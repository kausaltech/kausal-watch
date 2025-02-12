from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import apps
from django.contrib.admin.utils import quote, unquote
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import ProtectedError
from django.http.request import HttpRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext as _, gettext_lazy, ngettext_lazy
from django.views.generic import TemplateView
from wagtail.admin import messages
from wagtail.admin.views.generic.base import BaseObjectMixin, WagtailAdminTemplateMixin
from wagtail.admin.views.generic.permissions import PermissionCheckedMixin
from wagtail.permission_policies.base import AuthenticationOnlyPermissionPolicy
from wagtail.snippets import widgets as wagtailsnippets_widgets
from wagtail.snippets.views.snippets import DeleteView, IndexView

from wagtail_modeladmin.views import DeleteView as ModelAdminDeleteView, EditView, WMABaseView

from admin_site.utils import admin_req
from admin_site.viewsets import WatchCreateView, WatchEditView
from admin_site.wagtail import AplansCreateView, SetInstanceModelAdminMixin
from orgs.models import Organization

if TYPE_CHECKING:
    from django.http import HttpRequest


class OrganizationViewMixinOld:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        kwargs['parent_choices'] = Organization.objects.editable_by_user(self.request.user)
        # If the parent is not editable, the form would display an empty parent, leading to the org becoming a root when
        # saved. Prevent this by adding the parent to the queryset.
        if getattr(self, 'instance', None) and self.instance.get_parent():
            kwargs['parent_choices'] |= Organization.objects.filter(pk=self.instance.get_parent().pk)
        return kwargs


class OrganizationViewMixin:
    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['parent_choices'] = Organization.objects.editable_by_user(self.request.user)
        # If the parent is not editable, the form would display an empty parent,
        # leading to the org becoming a root when saved. Prevent this by adding
        # the parent to the queryset.
        if getattr(self, 'object', None) and self.object.get_parent():
            kwargs['parent_choices'] |= Organization.objects.filter(pk=self.object.get_parent().pk)
        return kwargs


class CreateChildNodeViewOld(OrganizationViewMixinOld, AplansCreateView):
    """View class that can take an additional URL param for parent id."""

    parent_pk = None

    def __init__(self, model_admin, parent_pk):
        self.parent_pk = unquote(parent_pk)
        object_qs = model_admin.model._default_manager.get_queryset()
        self.parent_instance = get_object_or_404(object_qs, pk=self.parent_pk)
        super().__init__(model_admin)

    def get_page_title(self):
        """Generate a title that explains you are adding a child."""
        title = super().get_page_title()
        return f'{title} child {self.opts.verbose_name} for {self.parent_instance}'

    def get_initial(self):
        """Set the selected parent field to the parent_pk."""
        return {'parent': self.parent_pk}


class CreateChildNodeView(OrganizationViewMixin, WatchCreateView):
    """
    View class that can take an additional URL param for parent id.

    Assumes that the url used to route to this view provides the primary key of
    the parent node as `parent_pk` attribute.
    """

    permission_required = 'add_child_node'

    def setup(self, request: HttpRequest, *args , **kwargs) -> None:
        self.parent_pk = unquote(kwargs['parent_pk'])
        self.parent_instance = get_object_or_404(self.get_queryset(), pk=self.parent_pk)
        return super().setup(request, *args, **kwargs)

    def user_has_permission(self, permission: str) -> bool:
        # A user can create an organization if they can edit *any* organization.
        # We just need to make sure that they can only create organizations that
        # are children of something they can edit.
        # TODO: Write tests to make sure we check in validation whether the user
        # has permissions depending on the chosen parent
        can_edit_parent = self.permission_policy.user_has_permission_for_instance(
            self.request.user, 'change', self.parent_instance
        )
        return can_edit_parent

    def get_page_subtitle(self):
        """Generate a title that explains you are adding a child."""
        return gettext_lazy('New child %(model)s for %(parent)s') % {
            'model': self.model._meta.verbose_name,
            'parent': self.parent_instance,
        }

    def get_initial(self):
        """Set the selected parent field to the parent_pk."""
        return {'parent': self.parent_pk}


class OrganizationCreateViewOld(OrganizationViewMixinOld, AplansCreateView):
    def form_valid(self, form):
        result = super().form_valid(form)
        # Add the new organization to the related organizations of the user's active plan
        org = form.instance
        plan = self.request.user.get_active_admin_plan()
        plan.related_organizations.add(org)
        return result

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            'plan': admin_req(self.request).user.get_active_admin_plan(),
        }


class OrganizationCreateView(OrganizationViewMixin, WatchCreateView):

    def form_valid(self, form):
        result = super().form_valid(form)
        # Add the new organization to the related organizations of the user's active plan
        org = form.instance
        plan = self.request.user.get_active_admin_plan()
        plan.related_organizations.add(org)
        return result


class OrganizationEditViewOld(OrganizationViewMixinOld, SetInstanceModelAdminMixin, EditView):

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),
            'plan': admin_req(self.request).user.get_active_admin_plan(),
        }


class OrganizationEditView(OrganizationViewMixin, WatchEditView):

    def user_has_permission(self, permission: str) -> bool:
        return self.permission_policy.user_has_permission_for_instance(admin_req(self.request).user, permission, self.object)


class Rollback(Exception):
    pass


def do_rollback():
    """
    Raise a Rollback exception.

    To be caught by the transaction.atomic() context manager to rollback the
    transaction.
    """
    raise Rollback()

class OrganizationDeleteViewOld(OrganizationViewMixinOld, SetInstanceModelAdminMixin, ModelAdminDeleteView):
    def confirmation_message(self):
        message = super().confirmation_message()
        if not self.instance:
            return message
        message += '\n' + _("This will delete the following objects:") + '\n'
        num_deleted_by_model = {}
        try:
            with transaction.atomic():
                num_deleted_by_model = self.instance.delete()[1]
                raise Rollback()
        except Rollback:
            pass
        except ProtectedError:
            # After confirming, the user will get an explanation why deletion didn't work
            return message
        items = []
        for model_identifier, num_deleted in num_deleted_by_model.items():
            model = apps.get_model(model_identifier)
            singular_str = "%(num_instances)d %(model_name_singular)s"
            plural_str = "%(num_instances)d %(model_name_plural)s"
            items.append(ngettext_lazy(singular_str, plural_str, num_deleted) % {
                'num_instances': num_deleted,
                'model_name_singular': model._meta.verbose_name,
                'model_name_plural': model._meta.verbose_name_plural,
            })
        message += ';\n'.join(items)
        return message


class OrganizationDeleteView(DeleteView):

    def user_has_permission(self, permission: str) -> bool:
        return self.permission_policy.user_has_permission_for_instance(admin_req(self.request).user, permission, self.object)

    @property
    def confirmation_message(self):
        message = super().confirmation_message
        if not self.object:
            return message
        message += '\n' + _("This will delete the following objects:") + '\n'
        num_deleted_by_model = {}
        try:
            with transaction.atomic():
                num_deleted_by_model = self.object.delete()[1]
                do_rollback()
        except Rollback:
            pass
        except ProtectedError:
            # After confirming, the user will get an explanation why deletion didn't work
            return message
        items = []
        for model_identifier, num_deleted in num_deleted_by_model.items():
            model = apps.get_model(model_identifier)
            singular_str = "%(num_instances)d %(model_name_singular)s"
            plural_str = "%(num_instances)d %(model_name_plural)s"
            items.append(ngettext_lazy(singular_str, plural_str, num_deleted) % {
                'num_instances': num_deleted,
                'model_name_singular': model._meta.verbose_name,
                'model_name_plural': model._meta.verbose_name_plural,
            })
        message += ';\n'.join(items)
        return message


class NodeIndexView(IndexView[Organization]):
    add_child_url_name = None

    def get_add_child_url(self, instance: Organization):
        return reverse(self.add_child_url_name, kwargs={'parent_pk': quote(instance.pk)})

    def get_add_child_button(self, instance: Organization):
        return wagtailsnippets_widgets.SnippetListingButton(
            url=self.get_add_child_url(instance),
            label=_("Add child"),
            icon_name='plus',
            attrs={'aria-label': _("Add child")},
        )

    def get_list_more_buttons(self, instance: Organization):
        buttons = super().get_list_more_buttons(instance)
        user = admin_req(self.request).user
        plan = user.get_active_admin_plan()

        # TODO: allow for organization metadata admins but without the huge
        # amount of db queries that iterating org.user_can_edit entails
        if user.is_general_admin_for_plan(plan):
            buttons.append(self.get_add_child_button(instance))

        return buttons


class OrganizationIndexView(NodeIndexView):
    # FIXME: in Wagtail 6.2.X this is the default, so this line can be deleted once we upgrade
    any_permission_required = ["add", "change", "delete", "view"]
    include_organization_in_active_plan_url_name = None
    exclude_organization_from_active_plan_url_name = None

    def get_add_child_button(self, instance: Organization):
        button = super().get_add_child_button(instance)
        button.label = _("Add suborganization")
        button.attrs['aria-label'] = _("Add suborganization")
        return button

    def get_include_organization_in_active_plan_url(self, instance: Organization):
        return reverse(self.include_organization_in_active_plan_url_name, kwargs={'pk': quote(instance.pk)})

    def get_exclude_organization_from_active_plan_url(self, instance: Organization):
        return reverse(self.exclude_organization_from_active_plan_url_name, kwargs={'pk': quote(instance.pk)})

    def include_organization_in_active_plan_button(self, instance: Organization):
        return wagtailsnippets_widgets.SnippetListingButton(
            url=self.get_include_organization_in_active_plan_url(instance),
            label=_("Include in active plan"),
            icon_name='link',
            attrs={'aria-label': _("Include this organization in the active plan")},
        )

    def exclude_organization_from_active_plan_button(self, instance: Organization):
        return wagtailsnippets_widgets.SnippetListingButton(
            url=self.get_exclude_organization_from_active_plan_url(instance),
            label=_("Exclude from active plan"),
            icon_name='fontawesome-link-slash',
            attrs={'aria-label': _("Exclude this organization from the active plan")},
        )

    def get_list_more_buttons(self, instance: Organization):
        # Wagtail does not check instance specific permissions when determining
        # the list buttons, so we set the permission policy temporarily to
        # AuthenticationOnlyPermissionPolicy that allows everything for
        # authenticated users to get all available buttons and then filter the
        # list ourselves with instance-specific rights.
        original_permission_policy = self.permission_policy
        self.permission_policy = AuthenticationOnlyPermissionPolicy(self.model)
        buttons = super().get_list_more_buttons(instance)
        self.permission_policy = original_permission_policy

        request = admin_req(self.request)
        user = request.user
        plan = user.get_active_admin_plan()

        if not self.permission_policy.user_has_permission_for_instance(user, 'change', instance):
            buttons = [button for button in buttons if button.url != self.get_edit_url(instance)]
        if not self.permission_policy.user_has_permission(user, 'add'):
            buttons = [button for button in buttons if button.url != self.get_copy_url(instance)]
        if not self.permission_policy.user_has_permission_for_instance(user, 'delete', instance):
            buttons = [button for button in buttons if button.url != self.get_delete_url(instance)]

        # Show "include in / exclude from active plan" button if user has permission and it's a root organization
        if instance.pk in plan.related_organizations.values_list('pk', flat=True):
            change_related_to_plan_button = self.exclude_organization_from_active_plan_button(instance)
        else:
            change_related_to_plan_button = self.include_organization_in_active_plan_button(instance)
        if instance.user_can_change_related_to_plan(self.request.user, plan) and instance.is_root():
            buttons.append(change_related_to_plan_button)

        return buttons


class SetOrganizationRelatedToActivePlanViewOld(WMABaseView):
    page_title = gettext_lazy("Add organization to active plan")
    org_pk = None
    set_related = True
    template_name = 'aplans/confirmation.html'

    def __init__(self, model_admin, org_pk, set_related=True):
        self.org_pk = unquote(org_pk)
        self.org = get_object_or_404(Organization, pk=self.org_pk)
        self.set_related = set_related
        super().__init__(model_admin)

    def check_action_permitted(self, user):
        plan = user.get_active_admin_plan()
        return self.org.user_can_change_related_to_plan(user, plan)

    @method_decorator(login_required)
    def dispatch(self, request, *args, **kwargs):
        if not self.check_action_permitted(request.user):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_meta_title(self):
        plan = self.request.user.get_active_admin_plan()
        if self.set_related:
            msg = _("Confirm including %(org)s in plan %(plan)s")
        else:
            msg = _("Confirm excluding %(org)s from plan %(plan)s")
        return msg % {'org': self.org, 'plan': plan}

    def confirmation_message(self):
        plan = self.request.user.get_active_admin_plan()
        if self.set_related:
            msg = _("Do you really want to include the organization '%(org)s' in the plan '%(plan)s'?")
        else:
            msg = _("Do you really want to exclude the organization '%(org)s' from the plan '%(plan)s'?")
        return msg % {'org': self.org, 'plan': plan}

    def add_to_plan(self, plan):
        if self.org.pk in plan.related_organizations.values_list('pk', flat=True):
            raise ValueError(_("The organization is already included in the plan"))
        plan.related_organizations.add(self.org)

    def remove_from_plan(self, plan):
        if self.org.pk not in plan.related_organizations.values_list('pk', flat=True):
            raise ValueError(_("The organization is not included in the plan"))
        plan.related_organizations.remove(self.org)

    def post(self, request, *args, **kwargs):
        plan = request.user.get_active_admin_plan()
        try:
            if self.set_related:
                self.add_to_plan(plan)
            else:
                self.remove_from_plan(plan)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(self.index_url)
        if self.set_related:
            msg = _("Organization '%(org)s' has been included in plan '%(plan)s'.")
        else:
            msg = _("Organization '%(org)s' has been excluded from plan '%(plan)s'.")
        messages.success(request, msg % {'org': self.org, 'plan': plan})
        return redirect(self.index_url)


class SetOrganizationRelatedToActivePlanView(
    BaseObjectMixin[Organization],
    PermissionCheckedMixin,
    WagtailAdminTemplateMixin,
    TemplateView,
):
    model = Organization
    permission_required = 'set_related_to_plan'
    page_title = gettext_lazy("Add organization to active plan")
    set_related = True
    template_name = 'aplans/confirmation.html'
    index_url_name: str | None = None

    def get_page_title(self):
        if self.set_related:
            return _("Add organization to active plan")
        return _("Exclude organization from active plan")

    def user_has_permission(self, permission):
        user = admin_req(self.request).user
        return self.permission_policy.user_has_permission_for_instance(user, permission, self.object)

    def get_page_subtitle(self):
        plan = admin_req(self.request).user.get_active_admin_plan()
        if self.set_related:
            msg = _("Confirm including %(org)s in plan %(plan)s")
        else:
            msg = _("Confirm excluding %(org)s from plan %(plan)s")
        return msg % {'org': self.object.name, 'plan': plan}

    def confirmation_message(self):
        plan = admin_req(self.request).user.get_active_admin_plan()
        if self.set_related:
            msg = _("Do you really want to include the organization '%(org)s' in the plan '%(plan)s'?")
        else:
            msg = _("Do you really want to exclude the organization '%(org)s' from the plan '%(plan)s'?")
        return msg % {'org': self.object.name, 'plan': plan}

    def add_to_plan(self, plan):
        if self.object.pk in plan.related_organizations.values_list('pk', flat=True):
            raise ValueError(_("The organization is already included in the plan"))
        plan.related_organizations.add(self.object)

    def remove_from_plan(self, plan):
        if self.object.pk not in plan.related_organizations.values_list('pk', flat=True):
            raise ValueError(_("The organization is not included in the plan"))
        plan.related_organizations.remove(self.object)

    def post(self, request, *args, **kwargs):
        plan = request.user.get_active_admin_plan()
        try:
            if self.set_related:
                self.add_to_plan(plan)
            else:
                self.remove_from_plan(plan)
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(self.index_url)
        if self.set_related:
            msg = _("Organization '%(org)s' has been included in plan '%(plan)s'.")
        else:
            msg = _("Organization '%(org)s' has been excluded from plan '%(plan)s'.")
        messages.success(request, msg % {'org': self.object.name, 'plan': plan})
        return redirect(self.index_url)

    @cached_property
    def index_url(self):
        return reverse(self.index_url_name)
