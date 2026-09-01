from __future__ import annotations

from typing import TYPE_CHECKING

from datasets.permission_policy import DataPointPermissionPolicyBase

if TYPE_CHECKING:
    from indicators.models import IndicatorGoalDataPoint  # noqa: F401


class IndicatorGoalDataPointPermissionPolicy(DataPointPermissionPolicyBase['IndicatorGoalDataPoint']):
    def __init__(self):
        from indicators.models.goal_data_point import IndicatorGoalDataPoint

        super().__init__(IndicatorGoalDataPoint)
