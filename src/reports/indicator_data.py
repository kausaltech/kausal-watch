from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from django.utils import translation

from indicators.models.action_links import ActionIndicator
from indicators.models.values import IndicatorGoal, IndicatorValue

if TYPE_CHECKING:
    import datetime
    from collections.abc import Sequence

    from actions.models.plan import Plan
    from indicators.models.indicator import Indicator


class IndicatorDataPoint(TypedDict):
    value: float
    date: str


class LinkedAction(TypedDict):
    id: int
    identifier: str
    name: str


class IndicatorReportData(TypedDict):
    """Indicator data shown in a report, either live or frozen in an `IndicatorSnapshot`."""

    identifier: str | None
    name: str
    unit: str
    organization: str
    linked_actions: list[LinkedAction]
    period_start_value: IndicatorDataPoint | None
    latest_value: IndicatorDataPoint | None
    target_value: IndicatorDataPoint | None


def _data_point(obj: IndicatorValue | IndicatorGoal | None) -> IndicatorDataPoint | None:
    if obj is None:
        return None
    return IndicatorDataPoint(value=obj.value, date=obj.date.isoformat())


def collect_indicator_report_data(
    indicators: Sequence[Indicator],
    plans: Sequence[Plan],
    period_start: datetime.date,
    language: str,
) -> dict[int, IndicatorReportData]:
    """
    Return the report data of each of `indicators`, keyed by indicator ID.

    Values are totals, i.e. without dimension categories. Linked actions are limited to those in `plans`.
    """
    if not indicators:
        return {}
    indicator_ids = [indicator.pk for indicator in indicators]
    period_start_values = {
        v.indicator_id: v
        for v in IndicatorValue.objects
        .filter(indicator_id__in=indicator_ids, categories__isnull=True, date__lte=period_start)
        .order_by('indicator_id', '-date')
        .distinct('indicator_id')
    }
    latest_values = {
        v.indicator_id: v
        for v in IndicatorValue.objects
        .filter(indicator_id__in=indicator_ids, categories__isnull=True)
        .order_by('indicator_id', '-date')
        .distinct('indicator_id')
    }
    target_values = {
        g.indicator_id: g
        for g in IndicatorGoal.objects
        .filter(indicator_id__in=indicator_ids)
        .order_by('indicator_id', '-date')
        .distinct('indicator_id')
    }
    action_links = (
        ActionIndicator.objects
        .filter(indicator_id__in=indicator_ids, action__plan__in=plans)
        .select_related('action')
        .order_by('action__plan_id', 'action__order')
    )
    with translation.override(language):
        linked_actions: dict[int, list[LinkedAction]] = {}
        for link in action_links:
            action = link.action
            linked_actions.setdefault(link.indicator_id, []).append(
                LinkedAction(id=action.pk, identifier=action.identifier, name=action.name_i18n)
            )
        return {
            indicator.pk: IndicatorReportData(
                identifier=indicator.identifier,
                name=indicator.name_i18n,
                unit=str(indicator.unit),
                organization=str(indicator.organization),
                linked_actions=linked_actions.get(indicator.pk, []),
                period_start_value=_data_point(period_start_values.get(indicator.pk)),
                latest_value=_data_point(latest_values.get(indicator.pk)),
                target_value=_data_point(target_values.get(indicator.pk)),
            )
            for indicator in indicators
        }
