from __future__ import annotations

import typing

from django.db.models import Q
from django.utils import timezone

from kausal_common.models.permission_policy import ModelPermissionPolicy, PermissionBlock

if typing.TYPE_CHECKING:
    from kausal_common.models.permission_policy import BaseObjectAction, ObjectSpecificAction

    from actions.models import Plan
    from actions.models.plan import PlanQuerySet  # noqa: F401
    from users.models import User


class PlanPermissionPolicy(ModelPermissionPolicy['Plan', None, 'PlanQuerySet']):
    def get_permission_block(
        self,
        action: BaseObjectAction,
        *,
        obj: Plan | None = None,
        context: None = None,
    ) -> PermissionBlock | None:
        if action == 'view' and obj is not None and not obj.is_active:
            return PermissionBlock('Inactive plans are not visible', code='plan_inactive')
        return super().get_permission_block(action, obj=obj, context=context)

    def construct_state_perm_q(self, action: ObjectSpecificAction) -> Q:
        if action == 'view':
            return Q(is_active=True)
        return Q()

    def construct_perm_q_anon(self, action: ObjectSpecificAction) -> Q | None:
        """
        Construct permission query for anonymous users.

        Allow viewing of plans if the expose_unpublished_plan_only_to_authenticated_user flag is False.
        If the expose_unpublished_plan_only_to_authenticated_user flag is True, only allow viewing of published plans.
        """
        if action == 'view':
            return Q(features__expose_unpublished_plan_only_to_authenticated_user=False) | Q(
                published_at__isnull=False,
                published_at__lte=timezone.now(),
            )
        return None

    def construct_perm_q(self, user: User, action: ObjectSpecificAction) -> Q | None:
        """
        Construct permission query for authenticated users.

        Inactive plans are excluded by the state-level permission filter.
        """
        if action == 'view':
            # get_adminable_plans() already filters out inactive plans for non-superusers,
            # and get_viewable_plans() also excludes inactive plans.
            viewable_plans = user.get_adminable_plans().union(user.get_viewable_plans()).values_list('id', flat=True)
            return (
                Q(id__in=viewable_plans)
                | Q(published_at__isnull=False, published_at__lte=timezone.now())
                | Q(features__expose_unpublished_plan_only_to_authenticated_user=False)
            )
        return None

    def user_has_perm(self, user: User, action: ObjectSpecificAction, obj: Plan) -> bool:
        """Check permissions for a specific plan instance."""
        if action == 'view':
            if not obj.is_active:
                return False
            if user.can_access_public_site(obj):
                return True
            if obj.features.expose_unpublished_plan_only_to_authenticated_user:
                return obj.published_at is not None and obj.published_at <= timezone.now()
            return True  # If expose_unpublished_plan_only_to_authenticated_user is False, allow access to Plan
        # Add other permission checks when needed
        return False

    def anon_has_perm(self, action: ObjectSpecificAction, obj: Plan) -> bool:
        """Check permissions for anonymous users."""
        if action == 'view':
            if not obj.is_active:
                return False
            if obj.features.expose_unpublished_plan_only_to_authenticated_user:
                return obj.published_at is not None and obj.published_at <= timezone.now()
            return True  # If expose_unpublished_plan_only_to_authenticated_user is False, allow access to Plan
        return False

    def user_can_create(self, user: User, context: None) -> bool:
        """Check if user can create new plans."""
        return False  # implement proper creation permissions when needed
