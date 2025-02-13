from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import apps
from django.contrib.admin.utils import unquote
from django.db import transaction
from django.db.models import ProtectedError
from django.http.request import HttpRequest
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _, gettext_lazy, ngettext_lazy
from django.views.generic import TemplateView
from wagtail.admin import messages
from wagtail.admin.views.generic.base import BaseObjectMixin, WagtailAdminTemplateMixin
from wagtail.admin.views.generic.permissions import PermissionCheckedMixin
from wagtail.snippets.views.snippets import DeleteView, IndexView

from admin_site.utils import admin_req
from admin_site.viewsets import WatchCreateView, WatchEditView
from orgs.models import Organization

if TYPE_CHECKING:
    from django.http import HttpRequest

    from orgs.wagtail_admin import OrganizationViewSet


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


class OrganizationCreateView(OrganizationViewMixin, WatchCreateView):

    def form_valid(self, form):
        result = super().form_valid(form)
        # Add the new organization to the related organizations of the user's active plan
        org = form.instance
        plan = self.request.user.get_active_admin_plan()
        plan.related_organizations.add(org)
        return result


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


class OrganizationIndexView(IndexView[Organization]):
    # FIXME: in Wagtail 6.2.X this is the default, so this line can be deleted once we upgrade
    any_permission_required = ["add", "change", "delete", "view"]
    view_set: OrganizationViewSet | None = None

    def get_list_more_buttons(self, instance: Organization):
        assert self.view_set is not None
        user = admin_req(self.request).user
        return self.view_set.get_index_view_buttons(user, instance, user.get_active_admin_plan())


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
