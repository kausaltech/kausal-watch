from __future__ import annotations

from wagtail.permission_policies.base import ModelPermissionPolicy

from kausal_common.users import user_or_none

from users.models import User

from .models import SiteGeneralContent


# FIXME: This is partly duplicated in actions/wagtail_admin.py.
class SiteGeneralContentPermissionPolicy(ModelPermissionPolicy[SiteGeneralContent, User]):
    def user_has_permission(self, user, action):
        user = user_or_none(user)
        if user is None:
            return False
        if action == 'view':
            return user.is_superuser
        if action == 'add':
            return user.is_superuser
        if action == 'change':
            return user.is_general_admin_for_plan(user.get_active_admin_plan())
        if action == 'delete':
            return False
        return super().user_has_permission(user, action)

    def user_has_permission_for_instance(self, user, action, instance):
        if action == 'change':
            return user.is_general_admin_for_plan(instance.plan)
        return super().user_has_permission_for_instance(user, action, instance)
