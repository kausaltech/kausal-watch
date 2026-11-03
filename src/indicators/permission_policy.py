from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q
from wagtail.permission_policies.base import ModelPermissionPolicy

from kausal_common.users import user_or_bust

from aplans.context_vars import ctx_request

from actions.models.plan import Plan
from admin_site.permissions import PlanRelatedPermissionPolicy
from datasets.permission_policy import DataPointPermissionPolicyBase
from indicators.models.dimensions import Dimension
from indicators.models.indicator import Indicator

if TYPE_CHECKING:
    from indicators.models import IndicatorGoalDataPoint  # noqa: F401
    from users.models import User


class IndicatorGoalDataPointPermissionPolicy(DataPointPermissionPolicyBase['IndicatorGoalDataPoint']):
    def __init__(self):
        from indicators.models.goal_data_point import IndicatorGoalDataPoint

        super().__init__(IndicatorGoalDataPoint)


class DimensionPermissionPolicy(PlanRelatedPermissionPolicy):
    """Give access to a dimension from the plans linked to it and the plans whose indicators use it."""

    def __init__(self):
        super().__init__(Dimension)

    def get_plans(self, obj: Dimension) -> list[Plan]:
        return list(Plan.objects.filter(Q(dimensions__dimension=obj) | Q(indicators__dimensions__dimension=obj)).distinct())


class IndicatorPermissionPolicy(ModelPermissionPolicy[Indicator]):
    """
    Add the plan roles to the model permissions of indicators.

    Creating needs plan admin rights, changing an indicator the right to modify it in the plan being
    edited, and deleting one admin rights in all plans that use it.
    """

    def __init__(self):
        super().__init__(Indicator)

    def user_has_permission(self, user, action):
        if not super().user_has_permission(user, action):
            return False
        if action != 'add':
            return True
        user = user_or_bust(user)
        return user.is_general_admin_for_plan(user.get_active_admin_plan())

    def user_has_permission_for_instance(self, user, action, instance):
        if not super().user_has_permission(user, action):
            return False
        user = user_or_bust(user)
        if action == 'view':
            if user.is_superuser:
                return True
            obj_plans = instance.plans.all()
            return any(plan in obj_plans for plan in user.get_adminable_plans())
        if action == 'change':
            # Editing an indicator here writes an indicator level (see IndicatorForm._save_m2m), so the
            # rights of the plan that the level belongs to decide it.
            return user.can_modify_indicator(instance, plan=self._get_plan_of_edit(user))
        if action == 'delete':
            return all(user.is_general_admin_for_plan(plan) for plan in instance.plans.all())
        return True

    def _get_plan_of_edit(self, user: User) -> Plan:
        """
        Return the plan whose rights decide about editing an indicator.

        Editing writes the indicator level of one plan, which is the active one unless the user
        switched plans while the form was open: IndicatorForm.save() then keeps writing for the plan
        the form was opened with, and the rights have to be checked for that same plan.
        """
        active_plan = user.get_active_admin_plan()
        if not ctx_request.is_set():
            return active_plan
        request = ctx_request.get()
        if request.method != 'POST':
            return active_plan
        initial_plan_id = request.session.get('initial_plan_id')
        if not initial_plan_id or str(initial_plan_id) == str(active_plan.id):
            return active_plan
        return Plan.objects.filter(id=initial_plan_id).first() or active_plan
