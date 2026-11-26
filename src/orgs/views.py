from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _, gettext_lazy
from django.views.generic import TemplateView
from wagtail.admin import messages
from wagtail.admin.views.generic.base import BaseObjectMixin, WagtailAdminTemplateMixin
from wagtail.admin.views.generic.permissions import PermissionCheckedMixin
from wagtail.snippets.views.snippets import CopyView

from kausal_common.organizations.views import (
    CreateChildNodeView as BaseCreateChildNodeView,
    OrganizationCreateView as BaseOrganizationCreateView,
    OrganizationDeleteView as BaseOrganizationDeleteView,
    OrganizationEditView as BaseOrganizationEditView,
    OrganizationIndexView as BaseOrganizationIndexView,
)
from kausal_common.users import user_or_bust

from admin_site.utils import admin_req
from orgs.models import Organization


class CreateChildNodeView(BaseCreateChildNodeView):
    pass


class OrganizationCreateView(BaseOrganizationCreateView):
    def form_valid(self, form):
        result = super().form_valid(form)
        # Add the new organization to the related organizations of the user's active plan
        org = form.instance
        plan = user_or_bust(self.request.user).get_active_admin_plan()
        plan.related_organizations.add(org)
        return result


# Fields that a copy must not take over from its source: identity, tree bookkeeping, revisions
# and audit fields. `path` and `depth` are kept so that the form can preselect the source's parent;
# treebeard assigns new ones when the copy is saved. `distinct_name` is not recomputed on save and
# would keep the source's name. The logo is left out because it may be an image from another
# tenant's collection, and sharing one image between organizations ties their media together.
_COPY_EXCLUDED_FIELDS = frozenset({
    'id',
    'uuid',
    'numchild',
    'distinct_name',
    'logo',
    'latest_revision',
    'created_time',
    'created_by',
    'last_modified_time',
    'last_modified_by',
})


class OrganizationCopyView(OrganizationCreateView, CopyView):
    """
    Create a new organization prefilled from an existing one.

    Wagtail's own copy view binds the form to the source object itself, so saving the "copy"
    overwrote the source. Organizations are shared across tenants and every admin may view all of
    them, so that let a plan admin rename or move another tenant's organization. Here the form is
    always bound to a new, unsaved instance.
    """

    def get_initial_form_instance(self) -> Organization:
        # Wagtail's `get_object` checks that the user may view or change the source. Deliberately
        # no super() call: Wagtail's implementation returns the source object itself.
        source: Organization = self.get_object()
        values = {
            field.attname: getattr(source, field.attname)
            for field in Organization._meta.concrete_fields
            if field.name not in _COPY_EXCLUDED_FIELDS
        }
        return Organization(**values)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Wagtail's create template posts to the add view. Post back here instead, so that the
        # copied fields which the form does not show (classification, dates, language) are kept.
        context['action_url'] = self.request.path
        return context

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # The base view also offers the instance's current parent even if the user cannot edit it,
        # so that editing does not silently turn an organization into a root. For a copy that
        # parent may belong to another tenant, so offer only the parents the user may edit.
        kwargs['parent_choices'] = Organization.get_parent_choices(user=admin_req(self.request).user)
        return kwargs


class OrganizationEditView(BaseOrganizationEditView):
    pass


class OrganizationDeleteView(BaseOrganizationDeleteView):
    pass


class OrganizationIndexView(BaseOrganizationIndexView):
    def get_list_more_buttons(self, instance: Organization):
        assert self.view_set is not None
        user = admin_req(self.request).user
        active_plan = user.get_active_admin_plan()
        return self.view_set.get_index_view_buttons(user, instance, active_plan)


class SetOrganizationRelatedToActivePlanView(
    BaseObjectMixin[Organization],
    PermissionCheckedMixin,
    WagtailAdminTemplateMixin,
    TemplateView,
):
    model = Organization
    permission_required = 'set_related_to_plan'
    page_title = gettext_lazy('Add organization to active plan')
    set_related = True
    template_name = 'aplans/confirmation.html'
    index_url_name: str | None = None

    def get_page_title(self):
        if self.set_related:
            return _('Add organization to active plan')
        return _('Exclude organization from active plan')

    def user_has_permission(self, permission):
        user = admin_req(self.request).user
        return self.permission_policy.user_has_permission_for_instance(user, permission, self.object)

    def get_page_subtitle(self):
        plan = admin_req(self.request).user.get_active_admin_plan()
        if self.set_related:
            msg = _('Confirm including %(org)s in plan %(plan)s')
        else:
            msg = _('Confirm excluding %(org)s from plan %(plan)s')
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
            raise ValueError(_('The organization is already included in the plan'))
        plan.related_organizations.add(self.object)

    def remove_from_plan(self, plan):
        if self.object.pk not in plan.related_organizations.values_list('pk', flat=True):
            raise ValueError(_('The organization is not included in the plan'))
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
