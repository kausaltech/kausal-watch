"""
Run the `search` GraphQL query through the Elasticsearch backend.

The resolver's querysets are compiled for real, for every kind of user and combination of
arguments, so a filter that the search index cannot serve fails the test instead of the
search on a live site.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from actions.tests.factories import ActionFactory, PlanFactory
from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

if TYPE_CHECKING:
    from actions.models import Plan

pytestmark = pytest.mark.django_db

SEARCH_QUERY = """
    query($plan: ID!, $query: String, $autocomplete: String, $includeRelatedPlans: Boolean, $onlyOtherPlans: Boolean) {
        search(
            plan: $plan, query: $query, autocomplete: $autocomplete,
            includeRelatedPlans: $includeRelatedPlans, onlyOtherPlans: $onlyOtherPlans
        ) {
            hits { id }
        }
    }
"""


def _make_user(kind: str, plan: Plan):
    if kind == 'anonymous':
        return None
    if kind == 'superuser':
        return UserFactory.create(is_superuser=True)
    user = UserFactory.create()
    PersonFactory.create(user=user, general_admin_plans=[plan] if kind == 'plan_admin' else [])
    return user


@pytest.fixture
def searched_plan() -> Plan:
    plan = PlanFactory.create()
    ActionFactory.create(plan=plan)
    IndicatorLevelFactory.create(indicator=IndicatorFactory.create(), plan=plan)
    return plan


@pytest.mark.parametrize('user_kind', ['anonymous', 'authenticated', 'plan_admin', 'superuser'])
@pytest.mark.parametrize('mode', ['query', 'autocomplete'])
@pytest.mark.parametrize(
    ('include_related_plans', 'only_other_plans'),
    [(False, False), (True, False), (False, True)],
)
def test_search_compiles_for_the_search_backend(
    client,
    graphql_client_query,
    es_requests,
    searched_plan,
    user_kind,
    mode,
    include_related_plans,
    only_other_plans,
) -> None:
    user = _make_user(user_kind, searched_plan)
    if user is not None:
        client.force_login(user)

    response = graphql_client_query(
        SEARCH_QUERY,
        variables={
            'plan': searched_plan.identifier,
            mode: 'climate',
            'includeRelatedPlans': include_related_plans,
            'onlyOtherPlans': only_other_plans,
        },
    )

    assert 'errors' not in response, response['errors']
    # One request per searched model: actions, pages and, unless only other plans are
    # searched, indicators.
    assert len(es_requests) == (2 if only_other_plans else 3)
