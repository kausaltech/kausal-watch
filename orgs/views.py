from __future__ import annotations

from django.shortcuts import redirect
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext as _, gettext_lazy
from django.views.generic import TemplateView
from wagtail.admin import messages
from wagtail.admin.views.generic.base import BaseObjectMixin, WagtailAdminTemplateMixin
from wagtail.admin.views.generic.permissions import PermissionCheckedMixin

from kausal_common.organizations.views import (
    CreateChildNodeView as BaseCreateChildNodeView,
    OrganizationCreateView as BaseOrganizationCreateView,
    OrganizationDeleteView as BaseOrganizationDeleteView,
    OrganizationEditView as BaseOrganizationEditView,
    OrganizationIndexView as BaseOrganizationIndexView,
)

from admin_site.utils import admin_req
from orgs.models import Organization


class CreateChildNodeView(BaseCreateChildNodeView):
    pass


class OrganizationCreateView(BaseOrganizationCreateView):
    pass


class OrganizationEditView(BaseOrganizationEditView):
    pass


class OrganizationDeleteView(BaseOrganizationDeleteView):
    pass

class OrganizationIndexView(BaseOrganizationIndexView):
    pass


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
