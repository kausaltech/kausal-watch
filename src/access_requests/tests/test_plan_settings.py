"""The sign-in page of an internal plan must be able to offer an access request."""

from __future__ import annotations

import pytest

from actions.tests.factories import PlanFactory

pytestmark = pytest.mark.django_db

WILDCARD_BASE = 'dummy.io'

QUERY = """
  query GetPlansByHostname($hostname: String) {
    plansForHostname(hostname: $hostname) {
      __typename
      accessRequestsEnabled
      accessRequestEligibilityText
    }
  }
"""


def _query_as_anonymous(graphql_client_query_data, settings, plan):
    settings.HOSTNAME_PLAN_DOMAINS = [WILDCARD_BASE]
    data = graphql_client_query_data(QUERY, variables={'hostname': f'{plan.identifier}.{WILDCARD_BASE}'})
    return data['plansForHostname'][0]


def test_internal_plan_sign_in_page_exposes_access_request_settings(graphql_client_query_data, settings):
    plan = PlanFactory.create(
        visibility='internal',
        access_request_eligibility_text='Only staff of the ministry are given access.',
        features__enable_access_requests=True,
    )
    plan_data = _query_as_anonymous(graphql_client_query_data, settings, plan)
    assert plan_data == {
        '__typename': 'RestrictedPlanNode',
        'accessRequestsEnabled': True,
        'accessRequestEligibilityText': 'Only staff of the ministry are given access.',
    }


def test_access_requests_are_off_by_default(graphql_client_query_data, settings):
    plan = PlanFactory.create(visibility='internal')
    plan_data = _query_as_anonymous(graphql_client_query_data, settings, plan)
    assert plan_data['accessRequestsEnabled'] is False
    assert plan_data['accessRequestEligibilityText'] is None
