from __future__ import annotations

import typing

from django.db.models import Q
from django.utils import timezone

from kausal_common.models.permission_policy import ModelPermissionPolicy, ObjectSpecificAction

if typing.TYPE_CHECKING:

    from actions.models import Plan
    from actions.models.plan import PlanQuerySet
    from users.models import User


class PlanPermissionPolicy(ModelPermissionPolicy['Plan', 'PlanQuerySet']):
    def construct_perm_q_anon(self, action: ObjectSpecificAction) -> Q | None:
        """
        Construct permission query for anonymous users.

        Allow viewing of plans if the expose_unpublished_plan_only_to_authenticated_user flag is False.
        If the expose_unpublished_plan_only_to_authenticated_user flag is True, only allow viewing of published plans.
        Inactive plans are never visible to anonymous users.
        """
        if action == 'view':
            return Q(is_active=True) & (
                Q(features__expose_unpublished_plan_only_to_authenticated_user=False)
                | Q(published_at__isnull=False, published_at__lte=timezone.now())
            )
        return None

    def construct_perm_q(self, user: User, action: ObjectSpecificAction) -> Q | None:
        """
        Construct permission query for authenticated users.

        Only superusers can see inactive plans. For non-superusers, inactive plans
        are excluded from both admin and public-facing access.
        """
        if action == 'view':
            # get_adminable_plans() already filters out inactive plans for non-superusers,
            # and get_viewable_plans() also excludes inactive plans.
            viewable_plans = user.get_adminable_plans().union(user.get_viewable_plans()).values_list("id", flat=True)
            return Q(id__in=viewable_plans) | (
                Q(is_active=True) & (
                    Q(published_at__isnull=False, published_at__lte=timezone.now())
                    | Q(features__expose_unpublished_plan_only_to_authenticated_user=False)
                )
            )
        return None

    def user_has_perm(self, user: User, action: ObjectSpecificAction, obj: Plan) -> bool:
        """Check permissions for a specific plan instance."""
        if action == 'view':
            if not obj.is_active:
                return user.is_superuser
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

    def user_can_create(self, user: User, context: PlanQuerySet) -> bool:
        """Check if user can create new plans."""
        return False  # implement proper creation permissions when needed
