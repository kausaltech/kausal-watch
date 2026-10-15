from __future__ import annotations

from typing import TYPE_CHECKING

from admin_site.permissions import PlanRelatedPermissionPolicy
from users.models import User

if TYPE_CHECKING:
    from django.contrib.auth.base_user import AbstractBaseUser
    from django.contrib.auth.models import AnonymousUser


class PledgePermissionPolicy(PlanRelatedPermissionPolicy):
    """Permission policy for Pledges - only accessible if community engagement is enabled."""

    def user_has_permission(self, user: AbstractBaseUser | AnonymousUser, action: str) -> bool:
        if not super().user_has_permission(user, action):
            return False

        # Check if community engagement is enabled
        from users.models import User

        if not isinstance(user, User):
            return False

        plan = user.get_active_admin_plan(required=False)
        if plan is None:
            return False

        return plan.features.enable_community_engagement


class ParticipantsPermissionPolicy(PlanRelatedPermissionPolicy):
    """
    Read-only for plan admins on plans that have community engagement enabled.

    Mirrors PledgePermissionPolicy's gating; the Participants UI is only
    meaningful when the underlying Pledge feature is enabled.
    """

    def user_has_permission(self, user: AbstractBaseUser | AnonymousUser, action: str) -> bool:
        if not super().user_has_permission(user, action):
            return False
        if not isinstance(user, User):
            return False
        plan = user.get_active_admin_plan(required=False)
        if plan is None:
            return False
        if not user.is_general_admin_for_plan(plan):
            return False
        if not plan.features.enable_community_engagement:
            return False
        return action == 'view'

    def user_has_any_permission(self, user, actions):
        return any(self.user_has_permission(user, a) for a in actions)
