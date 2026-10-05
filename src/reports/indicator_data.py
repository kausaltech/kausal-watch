from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from django.utils import translation

from indicators.models.action_links import ActionIndicator
from indicators.models.metadata import Unit
from indicators.models.values import IndicatorGoal, IndicatorValue
from orgs.models import Organization

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


def _organization_names(organizations: Sequence[Organization]) -> dict[int, str]:
    """Return `str()` of each organization, loading the ancestors its fully qualified name needs in one query."""
    ancestor_paths = {Organization._get_basepath(org.path, depth) for org in organizations for depth in range(1, org.depth)}
    orgs_by_path = Organization.make_orgs_by_path([*organizations, *Organization.objects.filter(path__in=ancestor_paths)])
    names: dict[int, str] = {}
    for org in organizations:
        name = org.get_fully_qualified_name(orgs_by_path)
        if org.dissolution_date:
            name += ' [dissolved]'
        names[org.pk] = name
    return names


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
    units = {unit.pk: unit for unit in Unit.objects.filter(indicators__in=indicator_ids).distinct()}
    organizations = {
        org.pk: org for org in Organization.objects.filter(pk__in={indicator.organization_id for indicator in indicators})
    }
    # The translated indicator name reads its default language from the organization
    for indicator in indicators:
        indicator.organization = organizations[indicator.organization_id]
    organization_names = _organization_names(list(organizations.values()))
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
                unit=str(units[indicator.unit_id]),
                organization=organization_names[indicator.organization_id],
                linked_actions=linked_actions.get(indicator.pk, []),
                period_start_value=_data_point(period_start_values.get(indicator.pk)),
                latest_value=_data_point(latest_values.get(indicator.pk)),
                target_value=_data_point(target_values.get(indicator.pk)),
            )
            for indicator in indicators
        }
