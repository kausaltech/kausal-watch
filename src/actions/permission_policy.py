from __future__ import annotations

import typing

from django.db.models import Q
from wagtail.permission_policies.base import ModelPermissionPolicy as WagtailModelPermissionPolicy

from kausal_common.models.permission_policy import ModelPermissionPolicy, PermissionBlock
from kausal_common.users import user_or_bust

from aplans.utils import RestrictedVisibilityModel

if typing.TYPE_CHECKING:
    from kausal_common.models.permission_policy import BaseObjectAction, ObjectSpecificAction

    from actions.models import Action, Plan
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

        `visibility` is the whole answer: a public plan is readable by anyone, an internal one
        by nobody who is not signed in. Whether the plan has been published is a property of its
        production surface and says nothing about who may read the plan.
        """
        if action == 'view':
            return Q(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
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
            return Q(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC) | Q(id__in=viewable_plans)
        return None

    def user_has_perm(self, user: User, action: ObjectSpecificAction, obj: Plan) -> bool:
        """Check permissions for a specific plan instance."""
        if action == 'view':
            if not obj.is_active:
                return False
            if obj.visibility == RestrictedVisibilityModel.VisibilityState.PUBLIC:
                return True
            return user.can_access_public_site(obj)
        # Add other permission checks when needed
        return False

    def anon_has_perm(self, action: ObjectSpecificAction, obj: Plan) -> bool:
        """Check permissions for anonymous users."""
        if action == 'view':
            if not obj.is_active:
                return False
            return obj.visibility == RestrictedVisibilityModel.VisibilityState.PUBLIC
        return False

    def user_can_create(self, user: User, context: None) -> bool:
        """Check if user can create new plans."""
        return False  # implement proper creation permissions when needed


class PlanAdminPermissionPolicy(WagtailModelPermissionPolicy):
    """
    Decide about plans in the Wagtail admin.

    Editing a plan needs general admin rights for it, and adding or deleting one is for superusers
    only. Everything else follows the Django model permissions.
    """

    def user_has_permission(self, user, action):
        if action in ('add', 'delete'):
            return user_or_bust(user).is_superuser
        return super().user_has_permission(user, action)

    def user_has_permission_for_instance(self, user, action, instance):
        if action == 'change':
            return user_or_bust(user).is_general_admin_for_plan(instance)
        return super().user_has_permission_for_instance(user, action, instance)


class ActionPermissionPolicy(WagtailModelPermissionPolicy):
    """
    Decide about actions in the Wagtail admin.

    On top of the Django model permissions, an action can only be acted on in its own plan while that
    plan is the active one, and the user's role in the plan decides what they may do with it.
    """

    def user_has_permission(self, user, action):
        if not super().user_has_permission(user, action):
            return False
        if action != 'add':
            return True
        user = user_or_bust(user)
        plan = user.get_active_admin_plan(required=False)
        return plan is not None and user.can_create_action(plan)

    def user_has_permission_for_instance(self, user, action, instance):
        user = user_or_bust(user)
        if instance.plan != user.get_active_admin_plan(required=False):
            return False
        return self.user_has_permission_in_own_plan(user, action, instance)

    def user_has_permission_in_own_plan(self, user: User, action: str, instance: Action) -> bool:
        """Decide like `user_has_permission_for_instance()`, but whichever plan is the active one."""
        # Deleting needs the right to change, as it did before actions had a permission policy
        if not super().user_has_permission(user, 'change' if action == 'delete' else action):
            return False
        if action == 'change':
            return user.can_modify_action(instance)
        if action == 'delete':
            plan = instance.plan
            return user.can_modify_action(instance) and not plan.actions_locked and user.is_general_admin_for_plan(plan)
        if action == 'publish':
            return user.can_publish_action(instance)
        return True
