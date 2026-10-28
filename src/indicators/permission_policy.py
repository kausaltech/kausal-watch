from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Q

from actions.models.plan import Plan
from admin_site.permissions import PlanRelatedPermissionPolicy
from datasets.permission_policy import DataPointPermissionPolicyBase
from indicators.models.dimensions import Dimension

if TYPE_CHECKING:
    from indicators.models import IndicatorGoalDataPoint  # noqa: F401


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
