import json

from django.conf import settings
from django.contrib.admin.utils import quote, unquote
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.text import capfirst
from django.utils.translation import gettext as _

from wagtail import hooks
from wagtail.admin import messages
from wagtail.admin.templatetags.wagtailadmin_tags import user_display_name
from wagtail.admin.utils import get_latest_str
from wagtail.locks import BasicLock, ScheduledForPublishLock, WorkflowLock
from wagtail.log_actions import log
from wagtail.log_actions import registry as log_registry
from wagtail.models import (
    DraftStateMixin,
    LockableMixin,
    RevisionMixin,
    WorkflowMixin,
    WorkflowState,
)
from wagtail.permissions import ModelPermissionPolicy

# The mixins in this file have been copied from Wagtail to avoid unexpected upstream changes. We use them in ActionAdmin
# for our MVP workflow functionality. They should be phased out ASAP by moving ActionAdmin to snippets.

class CreateEditViewOptionalFeaturesMixin:
    # Source: wagtail.admin.views.generic.CreateEditViewOptionalFeaturesMixin
    """
    A mixin for generic CreateView/EditView to support optional features that
    are applied to the model as mixins (e.g. DraftStateMixin, RevisionMixin).
    """

    view_name = "create"
    lock_url_name = None
    unlock_url_name = None
    revisions_unschedule_url_name = None
    workflow_history_url_name = None
    confirm_workflow_cancellation_url_name = None

    def setup(self, request, *args, **kwargs):
        # Need to set these here as they are used in get_object()
        self.request = request
        self.args = args
        self.kwargs = kwargs

        self.revision_enabled = self.model and issubclass(self.model, RevisionMixin)
        self.draftstate_enabled = self.model and issubclass(self.model, DraftStateMixin)
        self.locking_enabled = (
            self.model
            and issubclass(self.model, LockableMixin)
            and self.view_name != "create"
        )

        # Set the object before super().setup() as LocaleMixin.setup() needs it
        self.object = self.get_object()
        self.lock = self.get_lock()
        self.locked_for_user = self.lock and self.lock.for_user(request.user)
        super().setup(request, *args, **kwargs)

    @cached_property
    def workflow(self):
        if not self.model or not issubclass(self.model, WorkflowMixin):
            return None
        if self.object:
            return self.object.get_workflow()
        return self.model.get_default_workflow()

    @cached_property
    def workflow_enabled(self):
        return self.workflow is not None

    @cached_property
    def workflow_state(self):
        if not self.workflow_enabled or not self.object:
            return None
        return (
            self.object.current_workflow_state
            or self.object.workflow_states.order_by("created_at").last()
        )

    @cached_property
    def current_workflow_task(self):
        if not self.workflow_enabled or not self.object:
            return None
        return self.object.current_workflow_task

    @cached_property
    def workflow_tasks(self):
        if not self.workflow_state:
            return []
        return self.workflow_state.all_tasks_with_status()

    def user_has_permission(self, permission):
        user = self.request.user
        if user.is_superuser:
            return True

        # Workflow lock/unlock methods take precedence before the base
        # "lock" and "unlock" permissions -- see PagePermissionTester for reference
        if permission == "lock" and self.current_workflow_task:
            return self.current_workflow_task.user_can_lock(self.object, user)
        if permission == "unlock":
            # Allow unlocking even if the user does not have the 'unlock' permission
            # if they are the user who locked the object
            if self.object.locked_by_id == user.pk:
                return True
            if self.current_workflow_task:
                return self.current_workflow_task.user_can_unlock(self.object, user)

        # Check with base PermissionCheckedMixin logic
        has_base_permission = super().user_has_permission(permission)
        if has_base_permission:
            return True

        # Allow access to the editor if the current workflow task allows it,
        # even if the user does not normally have edit access. Users with edit
        # permissions can always edit regardless what this method returns --
        # see Task.user_can_access_editor() for reference
        if (
            permission == "change"
            and self.current_workflow_task
            and self.current_workflow_task.user_can_access_editor(
                self.object, self.request.user
            )
        ):
            return True

        return False

    def workflow_action_is_valid(self):
        if not self.current_workflow_task:
            return False
        self.workflow_action = self.request.POST.get("workflow-action-name")
        available_actions = self.current_workflow_task.get_actions(
            self.object, self.request.user
        )
        available_action_names = [
            name for name, verbose_name, modal in available_actions
        ]
        return self.workflow_action in available_action_names

    def get_available_actions(self):
        actions = [*super().get_available_actions()]

        if self.request.method != "POST":
            return actions

        if self.draftstate_enabled and (
            not self.permission_policy
            or self.permission_policy.user_has_permission(self.request.user, "publish")
        ):
            actions.append("publish")

        if self.workflow_enabled:
            actions.append("submit")

            if self.workflow_state and (
                self.workflow_state.user_can_cancel(self.request.user)
            ):
                actions.append("cancel-workflow")
                if self.object and not self.object.workflow_in_progress:
                    actions.append("restart-workflow")

            if self.workflow_action_is_valid():
                actions.append("workflow-action")

        return actions

    def get_object(self, queryset=None):
        if self.view_name == "create":
            return None
        self.live_object = super().get_object(queryset)
        if self.draftstate_enabled:
            return self.live_object.get_latest_revision_as_object()
        return self.live_object

    def get_lock(self):
        if not self.locking_enabled:
            return None
        return self.object.get_lock()

    def get_lock_url(self):
        if not self.locking_enabled or not self.lock_url_name:
            return None
        return reverse(self.lock_url_name, args=[quote(self.object.pk)])

    def get_unlock_url(self):
        if not self.locking_enabled or not self.unlock_url_name:
            return None
        return reverse(self.unlock_url_name, args=[quote(self.object.pk)])

    def get_workflow_history_url(self):
        if not self.workflow_enabled or not self.workflow_history_url_name:
            return None
        return reverse(self.workflow_history_url_name, args=[quote(self.object.pk)])

    def get_confirm_workflow_cancellation_url(self):
        if not self.workflow_enabled or not self.confirm_workflow_cancellation_url_name:
            return None
        return reverse(
            self.confirm_workflow_cancellation_url_name, args=[quote(self.object.pk)]
        )

    def get_error_message(self):
        if self.action == "cancel-workflow":
            return None
        if self.locked_for_user:
            return capfirst(
                _("The %(model_name)s could not be saved as it is locked")
                % {"model_name": self.model._meta.verbose_name}
            )
        return super().get_error_message()

    def get_success_message(self, instance=None):
        object = instance or self.object

        message = _("%(model_name)s '%(object)s' updated.")
        if self.view_name == "create":
            message = _("%(model_name)s '%(object)s' created.")

        if self.action == "publish":
            # Scheduled publishing
            if object.go_live_at and object.go_live_at > timezone.now():
                message = _(
                    "%(model_name)s '%(object)s' has been scheduled for publishing."
                )

                if self.view_name == "create":
                    message = _(
                        "%(model_name)s '%(object)s' created and scheduled for publishing."
                    )
                elif object.live:
                    message = _(
                        "%(model_name)s '%(object)s' is live and this version has been scheduled for publishing."
                    )

            # Immediate publishing
            else:
                message = _("%(model_name)s '%(object)s' updated and published.")
                if self.view_name == "create":
                    message = _("%(model_name)s '%(object)s' created and published.")

        if self.action == "submit":
            message = _(
                "%(model_name)s '%(object)s' has been submitted for moderation."
            )

            if self.view_name == "create":
                message = _(
                    "%(model_name)s '%(object)s' created and submitted for moderation."
                )

        if self.action == "restart-workflow":
            message = _("Workflow on %(model_name)s '%(object)s' has been restarted.")

        if self.action == "cancel-workflow":
            message = _("Workflow on %(model_name)s '%(object)s' has been cancelled.")

        return message % {
            "model_name": capfirst(self.model._meta.verbose_name),
            "object": get_latest_str(object),
        }

    def get_success_url(self):
        # If DraftStateMixin is enabled and the action is saving a draft
        # or cancelling a workflow, remain on the edit view
        remain_actions = {"create", "edit", "cancel-workflow"}
        if self.draftstate_enabled and self.action in remain_actions:
            return self.get_edit_url()
        return super().get_success_url()

    def save_instance(self):
        """
        Called after the form is successfully validated - saves the object to the db
        and returns the new object. Override this to implement custom save logic.
        """
        if self.draftstate_enabled:
            instance = self.form.save(commit=False)

            # If DraftStateMixin is applied, only save to the database in CreateView,
            # and make sure the live field is set to False.
            if self.view_name == "create":
                instance.live = False
                instance.save()
                self.form.save_m2m()
        else:
            instance = self.form.save()

        self.has_content_changes = self.view_name == "create" or self.form.has_changed()

        # Save revision if the model inherits from RevisionMixin
        self.new_revision = None
        if self.revision_enabled:
            self.new_revision = instance.save_revision(user=self.request.user)

        log(
            instance=instance,
            action="wagtail.create" if self.view_name == "create" else "wagtail.edit",
            revision=self.new_revision,
            content_changed=self.has_content_changes,
        )

        return instance

    def publish_action(self):
        hook_response = self.run_hook("before_publish", self.request, self.object)
        if hook_response is not None:
            return hook_response

        # Skip permission check as it's already done in get_available_actions
        self.new_revision.publish(user=self.request.user, skip_permission_checks=True)

        hook_response = self.run_hook("after_publish", self.request, self.object)
        if hook_response is not None:
            return hook_response

        return None

    def submit_action(self):
        if (
            self.workflow_state
            and self.workflow_state.status == WorkflowState.STATUS_NEEDS_CHANGES
        ):
            # If the workflow was in the needs changes state, resume the existing workflow on submission
            self.workflow_state.resume(self.request.user)
        else:
            # Otherwise start a new workflow
            self.workflow.start(self.object, self.request.user)

        return None

    def restart_workflow_action(self):
        self.workflow_state.cancel(user=self.request.user)
        self.workflow.start(self.object, self.request.user)
        return None

    def cancel_workflow_action(self):
        self.workflow_state.cancel(user=self.request.user)
        return None

    def workflow_action_action(self):
        extra_workflow_data_json = self.request.POST.get(
            "workflow-action-extra-data", "{}"
        )
        extra_workflow_data = json.loads(extra_workflow_data_json)
        self.object.current_workflow_task.on_action(
            self.object.current_workflow_task_state,
            self.request.user,
            self.workflow_action,
            **extra_workflow_data,
        )
        return None

    def run_action_method(self):
        action_method = getattr(self, self.action.replace("-", "_") + "_action", None)
        if action_method:
            return action_method()
        return None

    def form_valid(self, form):
        self.form = form
        with transaction.atomic():
            self.object = self.save_instance()

        response = self.run_action_method()
        if response is not None:
            return response

        response = self.save_action()

        hook_response = self.run_after_hook()
        if hook_response is not None:
            return hook_response

        return response

    def form_invalid(self, form):
        # Even if the object is locked due to not having permissions,
        # the original submitter can still cancel the workflow
        if self.action == "cancel-workflow":
            self.cancel_workflow_action()
            messages.success(
                self.request,
                self.get_success_message(),
                buttons=self.get_success_buttons(),
            )
            # Refresh the lock object as now WorkflowLock no longer applies
            self.lock = self.get_lock()
            self.locked_for_user = self.lock and self.lock.for_user(self.request.user)
        return super().form_invalid(form)

    def get_live_last_updated_info(self):
        # Create view doesn't have last updated info
        if self.view_name == "create":
            return None

        # DraftStateMixin is applied but object is not live
        if self.draftstate_enabled and not self.object.live:
            return None

        revision = None
        # DraftStateMixin is applied and object is live
        if self.draftstate_enabled and self.object.live_revision:
            revision = self.object.live_revision
        # RevisionMixin is applied, so object is assumed to be live
        elif self.revision_enabled and self.object.latest_revision:
            revision = self.object.latest_revision

        # No mixin is applied or no revision exists, fall back to latest log entry
        if not revision:
            return log_registry.get_logs_for_instance(self.object).first()

        return {
            "timestamp": revision.created_at,
            "user_display_name": user_display_name(revision.user),
        }

    def get_lock_context(self):
        if not self.locking_enabled:
            return {}

        user_can_lock = (
            not self.lock or isinstance(self.lock, WorkflowLock)
        ) and self.user_has_permission("lock")
        user_can_unlock = (
            isinstance(self.lock, BasicLock)
        ) and self.user_has_permission("unlock")
        user_can_unschedule = (
            isinstance(self.lock, ScheduledForPublishLock)
        ) and self.user_has_permission("publish")

        context = {
            "lock": self.lock,
            "locked_for_user": self.locked_for_user,
            "lock_url": self.get_lock_url(),
            "unlock_url": self.get_unlock_url(),
            "user_can_lock": user_can_lock,
            "user_can_unlock": user_can_unlock,
        }

        # Do not add lock message if the request method is not GET,
        # as POST request may add success/validation error messages already
        if not self.lock or self.request.method != "GET":
            return context

        lock_message = self.lock.get_message(self.request.user)
        if lock_message:
            if user_can_unlock:
                lock_message = format_html(
                    '{} <span class="buttons"><button type="button" class="button button-small button-secondary" data-action="w-action#post" data-controller="w-action" data-w-action-url-value="{}">{}</button></span>',
                    lock_message,
                    self.get_unlock_url(),
                    _("Unlock"),
                )

            if user_can_unschedule:
                lock_message = format_html(
                    '{} <span class="buttons"><button type="button" class="button button-small button-secondary" data-action="w-action#post" data-controller="w-action" data-w-action-url-value="{}">{}</button></span>',
                    lock_message,
                    reverse(
                        self.revisions_unschedule_url_name,
                        args=[quote(self.object.pk), self.object.scheduled_revision.id],
                    ),
                    _("Cancel scheduled publish"),
                )

            if (
                not isinstance(self.lock, ScheduledForPublishLock)
                and self.locked_for_user
            ):
                messages.warning(self.request, lock_message, extra_tags="lock")
            else:
                messages.info(self.request, lock_message, extra_tags="lock")

        return context

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.get_lock_context())
        context["revision_enabled"] = self.revision_enabled
        context["draftstate_enabled"] = self.draftstate_enabled
        context["workflow_enabled"] = self.workflow_enabled
        context["live_last_updated_info"] = self.get_live_last_updated_info()
        context["workflow_history_url"] = self.get_workflow_history_url()
        context[
            "confirm_workflow_cancellation_url"
        ] = self.get_confirm_workflow_cancellation_url()
        context["publishing_will_cancel_workflow"] = getattr(
            settings, "WAGTAIL_WORKFLOW_CANCEL_ON_PUBLISH", True
        ) and bool(self.workflow_tasks)
        return context

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        # Make sure object is not locked
        if not self.locked_for_user and form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)


class HookResponseMixin:
    # Source: wagtail.admin.views.generic.mixins.HookResponseMixin
    """
    A mixin for class-based views to run hooks by `hook_name`.
    """

    def run_hook(self, hook_name, *args, **kwargs):
        """
        Run the named hook, passing args and kwargs to each function registered under that hook name.
        If any return an HttpResponse, stop processing and return that response
        """
        for fn in hooks.get_hooks(hook_name):
            result = fn(*args, **kwargs)
            if hasattr(result, "status_code"):
                return result
        return None


class BeforeAfterHookMixin(HookResponseMixin):
    # Source: wagtail.admin.views.generic.mixins.BeforeAfterHookMixin
    """
    A mixin for class-based views to support hooks like `before_edit_page` and
    `after_edit_page`, which are triggered during execution of some operation and
    can return a response to halt that operation and/or change the view response.
    """

    def run_before_hook(self):
        """
        Define how to run the hooks before the operation is executed.
        The `self.run_hook(hook_name, *args, **kwargs)` from HookResponseMixin
        can be utilised to call the hooks.

        If this method returns a response, the operation will be aborted and the
        hook response will be returned as the view response, skipping the default
        response.
        """
        return None

    def run_after_hook(self):
        """
        Define how to run the hooks after the operation is executed.
        The `self.run_hook(hook_name, *args, **kwargs)` from HookResponseMixin
        can be utilised to call the hooks.

        If this method returns a response, it will be returned as the view
        response immediately after the operation finishes, skipping the default
        response.
        """
        return None

    def dispatch(self, *args, **kwargs):
        hooks_result = self.run_before_hook()
        if hooks_result is not None:
            return hooks_result

        return super().dispatch(*args, **kwargs)

    def form_valid(self, form):
        response = super().form_valid(form)

        hooks_result = self.run_after_hook()
        if hooks_result is not None:
            return hooks_result

        return response


class GenericModelEditViewMixin(BeforeAfterHookMixin):
    # Source: wagtail.admin.views.generic.models.EditView
    success_message = None
    actions = ["edit"]

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.action = self.get_action(request)

    def get_action(self, request):
        for action in self.get_available_actions():
            if request.POST.get(f"action-{action}"):
                return action
        return "edit"

    def get_available_actions(self):
        return self.actions

    def save_action(self):
        success_message = self.get_success_message()
        success_buttons = self.get_success_buttons()
        if success_message is not None:
            messages.success(
                self.request,
                success_message,
                buttons=success_buttons,
            )
        return redirect(self.get_success_url())

    def get_success_message(self):
        if self.success_message is None:
            return None
        return self.success_message % {"object": self.object}

    def get_success_buttons(self):
        return [
            messages.button(
                reverse(self.edit_url_name, args=(quote(self.object.pk),)), _("Edit")
            )
        ]

    def get_edit_url(self):
        if not self.edit_url_name:
            raise ImproperlyConfigured(
                "Subclasses of wagtail.admin.views.generic.models.EditView must provide an "
                "edit_url_name attribute or a get_edit_url method"
            )
        return reverse(self.edit_url_name, args=(quote(self.object.pk),))


class PermissionCheckedMixin:
    # Source: wagtail.admin.views.generic.permissions.PermissionCheckedMixin
    """
    Mixin for class-based views to enforce permission checks according to
    a permission policy (see wagtail.permission_policies).

    To take advantage of this, subclasses should set the class property:
    * permission_policy (a policy object)
    and either of:
    * permission_required (an action name such as 'add', 'change' or 'delete')
    * any_permission_required (a list of action names - the user must have
      one or more of those permissions)
    """

    permission_policy = None
    permission_required = None
    any_permission_required = None

    def dispatch(self, request, *args, **kwargs):
        if self.permission_policy is not None:

            if self.permission_required is not None:
                if not self.user_has_permission(self.permission_required):
                    raise PermissionDenied

            if self.any_permission_required is not None:
                if not self.user_has_any_permission(self.any_permission_required):
                    raise PermissionDenied

        return super().dispatch(request, *args, **kwargs)

    def user_has_permission(self, permission):
        return self.permission_policy.user_has_permission(self.request.user, permission)

    def user_has_any_permission(self, permissions):
        return self.permission_policy.user_has_any_permission(
            self.request.user, permissions
        )


class SnippetsEditViewCompatibilityMixin(
    CreateEditViewOptionalFeaturesMixin,
    GenericModelEditViewMixin,
    PermissionCheckedMixin,
):
    # Source: wagtail.snippets.views.snippets.EditView and other classes
    view_name = "edit"
    pk_url_kwarg = 'instance_pk'
    permission_required = 'change'

    def __init__(self, *args, **kwargs):
        # Our own hack
        super().__init__(*args, **kwargs)
        self.edit_url_name = self.url_helper.get_action_url_name('edit')

    def setup(self, request, *args, **kwargs):
        # Our own hack
        super().setup(request, *args, **kwargs)
        self.instance = self.object
        # Only use some of the hacks if the plan uses workflows
        if not self.instance.plan.features.enable_moderation_workflow:
            # FIXME: Some code in super().setup() already ran with other values for this. Hopefully nothing breaks.
            self.revision_enabled = False
            self.draftstate_enabled = False
            self.locking_enabled = False

    def run_before_hook(self):
        return self.run_hook("before_edit_snippet", self.request, self.object)

    def run_after_hook(self):
        return self.run_hook("after_edit_snippet", self.request, self.object)

    # Stuff from other classes
    def get(self, request, *args, **kwargs):
        # Copied from django.views.generic.edit.BaseUpdateView; omitting causes problems with
        # CreateEditViewOptionalFeaturesMixin
        self.object = self.get_object()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        # Copied from django.views.generic.edit.BaseUpdateView; omitting causes problems with
        # CreateEditViewOptionalFeaturesMixin
        self.object = self.get_object()
        return super().post(request, *args, **kwargs)

    def get_object(self, queryset=None):
        # Copied and adapted from wagtail.admin.views.generic.models.EditView.get_object()
        if 'instance_pk' not in self.kwargs:
            self.kwargs['instance_pk'] = self.instance_pk
        self.kwargs['instance_pk'] = unquote(str(self.kwargs['instance_pk']))
        return super().get_object(queryset)

    @property
    def permission_policy(self):
        # Copied from wagtail.snippets.views.snippets.SnippetViewSet
        return ModelPermissionPolicy(self.model)
