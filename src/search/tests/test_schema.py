from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, cast

from django.utils.timezone import make_aware

import pytest

from actions.models import Plan
from actions.tests.factories import PlanFactory
from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory
from search.schema import SearchResults

if TYPE_CHECKING:
    from aplans.graphql_types import GQLInfo

pytestmark = pytest.mark.django_db


@pytest.fixture
def indicator_shared_between_plans():
    """Link an indicator to an older unpublished plan and to a published one."""
    older_plan = PlanFactory.create(published_at=None)
    searched_plan = PlanFactory.create()
    Plan.objects.filter(pk=older_plan.pk).update(created_at=make_aware(datetime.datetime(2020, 1, 1)))  # noqa: DTZ001
    Plan.objects.filter(pk=searched_plan.pk).update(created_at=make_aware(datetime.datetime(2024, 1, 1)))  # noqa: DTZ001
    indicator = IndicatorFactory.create()
    IndicatorLevelFactory.create(indicator=indicator, plan=older_plan)
    IndicatorLevelFactory.create(indicator=indicator, plan=searched_plan)
    indicator.relevance = 1.0
    return indicator, older_plan, searched_plan


def test_indicator_hit_is_bound_to_a_searched_plan(indicator_shared_between_plans) -> None:
    indicator, older_plan, searched_plan = indicator_shared_between_plans
    assert indicator.plans.first() == older_plan

    hits = SearchResults.resolve_hits({'hits': [indicator], 'plan_ids': [searched_plan.pk]}, cast('GQLInfo', None))

    assert [hit.plan for hit in hits] == [searched_plan]


def test_indicator_hit_outside_the_searched_plans_is_dropped(indicator_shared_between_plans) -> None:
    indicator, _older_plan, _searched_plan = indicator_shared_between_plans

    hits = SearchResults.resolve_hits({'hits': [indicator], 'plan_ids': []}, cast('GQLInfo', None))

    assert hits == []
