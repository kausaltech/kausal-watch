from __future__ import annotations

import json

import pytest

from actions.tests.factories import PlanFactory
from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory

pytestmark = pytest.mark.django_db


PLAN_INDICATORS_QUERY = """
query planIndicators($plan: ID!) {
  planIndicators(plan: $plan) {
    identifier
  }
}
"""

RELATED_PLAN_INDICATORS_QUERY = """
query relatedPlanIndicators($plan: ID!) {
  relatedPlanIndicators(plan: $plan) {
    identifier
  }
}
"""

SINGLE_INDICATOR_QUERY = """
query indicator($plan: ID!, $id: ID!) {
  indicator(plan: $plan, id: $id) {
    identifier
  }
}
"""


@pytest.fixture
def listed_indicator(plan):
    indicator = IndicatorFactory.create(hide_from_indicator_list=False)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    return indicator


@pytest.fixture
def hidden_indicator(plan):
    indicator = IndicatorFactory.create(hide_from_indicator_list=True)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    return indicator


def _identifiers(response, field):
    assert 'errors' not in response, json.dumps(response)
    return {row['identifier'] for row in response['data'][field]}


class TestHideFromIndicatorList:
    """An indicator flagged hidden drops out of the public UI lists but stays reachable directly."""

    def test_plan_indicators_excludes_hidden(self, plan, listed_indicator, hidden_indicator, graphql_client_query):
        response = graphql_client_query(PLAN_INDICATORS_QUERY, variables={'plan': plan.identifier})
        assert _identifiers(response, 'planIndicators') == {listed_indicator.identifier}

    def test_related_plan_indicators_excludes_hidden(self, plan, graphql_client_query):
        related_plan = PlanFactory.create()
        related_plan.related_plans.add(plan)
        listed = IndicatorFactory.create(hide_from_indicator_list=False)
        hidden = IndicatorFactory.create(hide_from_indicator_list=True)
        for indicator in (listed, hidden):
            IndicatorLevelFactory.create(indicator=indicator, plan=related_plan)

        response = graphql_client_query(RELATED_PLAN_INDICATORS_QUERY, variables={'plan': plan.identifier})
        assert _identifiers(response, 'relatedPlanIndicators') == {listed.identifier}

    def test_hidden_indicator_still_reachable_directly(self, plan, hidden_indicator, graphql_client_query):
        response = graphql_client_query(
            SINGLE_INDICATOR_QUERY, variables={'plan': plan.identifier, 'id': str(hidden_indicator.id)}
        )
        assert 'errors' not in response, json.dumps(response)
        assert response['data']['indicator']['identifier'] == hidden_indicator.identifier
