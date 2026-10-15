from __future__ import annotations

from typing import TYPE_CHECKING

from wagtail.permission_policies.base import ModelPermissionPolicy

from kausal_common.users import is_authenticated

from users.models import User

from .models import UserFeedback
from .views import SetUserFeedbackProcessedView

if TYPE_CHECKING:
    from kausal_common.users import UserOrAnon


class UserFeedbackPermissionPolicy(ModelPermissionPolicy[UserFeedback, User, str]):
    def user_has_permission(self, user: UserOrAnon, action: str) -> bool:
        if not is_authenticated(user):
            return False
        if action in ('add', 'change'):
            return False
        if action == 'view':
            return True
        if action == 'delete':
            return user.is_general_admin_for_plan(user.get_active_admin_plan())

        return super().user_has_permission(user, action)

    def user_has_permission_for_instance(self, user: User, action: str, instance: UserFeedback) -> bool:
        if action == 'delete':
            return user.is_general_admin_for_plan(instance.plan)
        if action == SetUserFeedbackProcessedView.permission_required:
            return instance.user_can_change_is_processed(user)

        return super().user_has_permission_for_instance(user, action, instance)
