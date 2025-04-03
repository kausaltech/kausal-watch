from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _

from kausal_common.models.roles import (
    # ALL_MODEL_PERMS,
    AdminRole,
    InstanceFieldGroupRole,
    # InstanceSpecificRole,
    register_role,
)

from aplans.const import (
    PLAN_ADMIN_ROLE,
    # PLAN_VIEWER_ROLE,
)

if TYPE_CHECKING:
    from django.contrib.auth.models import Group
    from wagtail.models.sites import Site

    from actions.models import Plan


class InstanceGroupMembershipRole(InstanceFieldGroupRole['Plan']):
    def __init__(self):
        from .models import Plan
        super().__init__(Plan)

    def get_instance_group_name(self, obj: Plan) -> str:
        assert obj is not None
        return '%s %s' % (obj.name, self.group_name)

    def get_instance_site(self, obj: Plan) -> Site | None:
        return obj.site


class PlanAdminRole(InstanceGroupMembershipRole, AdminRole['Plan']):
    id = PLAN_ADMIN_ROLE
    name = _("General admin")
    group_name = "General admins"
    instance_group_field_name = 'admin_group'

    model_perms = AdminRole.model_perms + [
        ('actions', ('plan', 'action'), ('view', 'change')),
    ]

    def get_existing_instance_group(self, obj: Plan) -> Group | None:
        return obj.admin_group

    def update_instance_group(self, obj: Plan, group: Group | None):
        obj.admin_group = group
        obj.save(update_fields=[self.instance_group_field_name])


# TODO: Either remove this or add field `viewer_group` to the Plan model
# class PlanViewerRole(InstanceGroupMembershipRole, InstanceSpecificRole['Plan']):
#     id = PLAN_VIEWER_ROLE
#     name = _('Viewer')
#     group_name = "Viewer"
#     instance_group_field_name = 'viewer_group'
#
#     model_perms = [
#         ('actions', ('plan', 'action', 'indicator'), ('view',)),
#     ]
#
#     def get_existing_instance_group(self, obj: Plan) -> Group | None:
#         return obj.viewer_group
#
#     def update_instance_group(self, obj: Plan, group: Group | None):
#         obj.viewer_group = group
#         obj.save(update_fields=[self.instance_group_field_name])


plan_admin_role = PlanAdminRole()
# plan_viewer_role = PlanViewerRole()

register_role(plan_admin_role)
# register_role(plan_viewer_role)
