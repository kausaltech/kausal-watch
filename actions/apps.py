from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

from django.apps import AppConfig
from django.contrib.admin.filters import SimpleListFilter
from django.utils.translation import gettext_lazy as _

from kausal_common.users import user_or_bust

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.http.request import HttpRequest
    from wagtail.models import Collection

    from wagtail_modeladmin.options import ModelAdmin

    from users.models import User

_wagtail_image_chooser_viewset_permission_policy = None
_wagtail_get_base_snippet_action_menu_items = None


def _get_collections(user: User) -> Iterable[Collection]:
    plan = user.get_active_admin_plan()
    if plan.root_collection is None:
        return []
    return plan.root_collection.get_descendants(inclusive=True)


class CollectionFilter(SimpleListFilter):
    title = _('collection')
    parameter_name = 'collection'

    def lookups(self, request: HttpRequest, model_admin: ModelAdmin) -> list[tuple[str, str]]:
        user = user_or_bust(request.user)
        collections = _get_collections(user)
        return [(str(collection.pk), str(collection)) for collection in collections]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(collection=self.value())
        return None


def get_unfiltered_object_list(self):
    collections = _get_collections(self.request.user)
    return self.model.objects.filter(collection__in=collections)


def monkeypatch_image_chooser_viewset():
    from wagtail.images.views.chooser import ImageChooserViewSet

    from images.permissions import permission_policy
    global _wagtail_image_chooser_viewset_permission_policy  # noqa: PLW0603

    if _wagtail_image_chooser_viewset_permission_policy is None:
        _wagtail_image_chooser_viewset_permission_policy  = ImageChooserViewSet.permission_policy
        ImageChooserViewSet.permission_policy = permission_policy


@cache
def get_base_snippet_action_menu_items(model):
    from actions.models.action import Action
    if model == Action:
        from wagtail.models import DraftStateMixin, LockableMixin, WorkflowMixin
        from wagtail.snippets.action_menu import (
            CancelWorkflowMenuItem as WagtailCancelWorkflowMenuItem,
            DeleteMenuItem,
            LockedMenuItem,
            PublishMenuItem as WagtailPublishMenuItem,
            RestartWorkflowMenuItem as WagtailRestartWorkflowMenuItem,
            SaveMenuItem,
            SubmitForModerationMenuItem as WagtailSubmitForModerationMenuItem,
            # UnpublishMenuItem as WagtailUnpublishMenuItem,
        )

        class RestartWorkflowMenuItem(WagtailRestartWorkflowMenuItem):
            label = _("Resubmit for moderation")

        class CancelWorkflowMenuItem(WagtailCancelWorkflowMenuItem):
            label = _("Cancel moderation")

        class PublishMenuItem(WagtailPublishMenuItem):
            def is_shown(self, context) -> bool:
                user = user_or_bust(context['request'].user)
                instance = context['instance']
                return (super().is_shown(context)
                        and user.can_publish_action(instance)
                        and not instance.workflow_in_progress)  # If a workflow is in progress, use "approve" instead


        class SubmitForModerationMenuItem(WagtailSubmitForModerationMenuItem):
            def is_shown(self, context) -> bool:
                if not super().is_shown(context):
                    return False

                instance = context['instance']
                workflow_state = instance.current_workflow_state if instance else None
                in_moderation = workflow_state and workflow_state.status == workflow_state.STATUS_NEEDS_CHANGES

                workflow = instance.get_workflow()
                if workflow.tasks.count() > 1:
                    """
                    In multiple-task workflows, there needs to be a way for
                    the moderator to initiate the workflow because otherwise
                    the moderator has no way to pass the object along the
                    workflow to the next moderation task.

                    FIXME: optimally there would be a way for a moderator to
                    start the workflow immediately from the second task if the
                    editor hasn't initiated the first task. Now the moderator
                    has to first submit, then approve if nobody has originally
                    submitted.
                    """
                    return True

                if in_moderation:
                    # Don't show "Resubmit" because then "Restart workflow" is what we probably want as it sends notifications to the
                    # reviewers again.
                    # FIXME: handle this in the multiple-task workflow case
                    return False

                user = context['request'].user
                if user.can_approve_action(instance):
                    # In one-task workflows, sending for moderation is redundant because they can publish immediately.
                    return False
                return True

        # class UnpublishMenuItem(WagtailUnpublishMenuItem):
        #     def is_shown(self, context):
        #         user = context["request"].user
        #         return super().is_shown(context) and user.can_publish_action(context['instance'])

        menu_items = []
        # WorkflowMenuItem instances are inserted with order 100
        menu_items += [
            # SaveMenuItem(order=101),  # We want "Publish" (below) or "Approve" (100) as the default action (if shown)
            # FIXME: The previous line would cause "SaveMenuItem" to be not the first item, so the first item would
            # probably be a workflow-related item. This causes a problem because Wagtail in `workflow-action.js`
            # only appends hidden input elements to the form if the "more actions" dropdown is expanded. That is,
            # the default button must not be workflow-related. Otherwise Wagtail wouldn't handle the workflow
            # action properly. This should better be fixed in the Wagtail code, but until we find a good
            # solution, let's just live with a suboptimal menu item order.
            SaveMenuItem(order=0),
            DeleteMenuItem(order=102),
        ]
        if issubclass(model, DraftStateMixin):
            menu_items += [
                # UnpublishMenuItem(order=20),
                # PublishMenuItem(order=30),
                PublishMenuItem(order=5),
            ]
        if issubclass(model, WorkflowMixin):
            menu_items += [
                SubmitForModerationMenuItem(order=40),
                RestartWorkflowMenuItem(order=50),
                CancelWorkflowMenuItem(order=60),
            ]
        if issubclass(model, LockableMixin):
            menu_items.append(LockedMenuItem(order=10000))

        return menu_items
    return _wagtail_get_base_snippet_action_menu_items(model)


def monkeypatch_snippet_action_menu():
    from wagtail.snippets import action_menu
    global _wagtail_get_base_snippet_action_menu_items

    if _wagtail_get_base_snippet_action_menu_items is None:
        _wagtail_get_base_snippet_action_menu_items = action_menu.get_base_snippet_action_menu_items
        action_menu.get_base_snippet_action_menu_items = get_base_snippet_action_menu_items


class ActionsConfig(AppConfig):
    name = 'actions'
    verbose_name = _('Actions')

    def ready(self):
        # monkeypatch filtering of Collections
        monkeypatch_image_chooser_viewset()
        monkeypatch_snippet_action_menu()
        import actions.signals
        actions.signals.register_signal_handlers()
