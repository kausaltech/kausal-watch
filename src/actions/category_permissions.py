from __future__ import annotations

from admin_site.permissions import PlanRelatedPermissionPolicy


class CategoryPermissionPolicy(PlanRelatedPermissionPolicy):
    """Also require the category type's edit rights to change or delete a category."""

    def user_has_permission_for_instance(self, user, action, instance) -> bool:
        if not super().user_has_permission_for_instance(user, action, instance):
            return False
        if action not in ('change', 'delete'):
            return True
        return instance.type.is_instance_editable_by(user, instance.type.plan, None)
