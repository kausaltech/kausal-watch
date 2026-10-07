from __future__ import annotations

import json

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest

from aplans.utils import RestrictedVisibilityModel

from actions.tests.factories import ActionFactory, CategoryFactory, CategoryTypeFactory, PlanFactory

pytestmark = pytest.mark.django_db

PLAN_CATEGORIES_QUERY = """
query($plan: ID!) {
  planCategories(plan: $plan) {
    identifier
    actions {
      identifier
      name
    }
  }
}
"""

# `category` is resolved without the query optimizer, so its actions take the resolver's fallback path.
CATEGORY_QUERY = """
query($plan: ID!, $categoryType: ID!, $category: ID!) {
  category(plan: $plan, categoryType: $categoryType, externalIdentifier: $category) {
    actions {
      identifier
    }
  }
}
"""


@pytest.mark.parametrize('grow', ['actions', 'categories'])
def test_query_count_does_not_grow(graphql_client_query_data, grow):
    plan = PlanFactory.create()
    category_type = CategoryTypeFactory.create(plan=plan)
    category = CategoryFactory.create(type=category_type)

    def count_queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            graphql_client_query_data(PLAN_CATEGORIES_QUERY, variables={'plan': plan.identifier})
        return len(ctx.captured_queries)

    ActionFactory.create(plan=plan, categories=[category])
    queries_for_one = count_queries()
    for _ in range(3):
        if grow == 'categories':
            category = CategoryFactory.create(type=category_type)
        ActionFactory.create(plan=plan, categories=[category])
    assert count_queries() == queries_for_one


class TestCategoryActionsVisibility:
    """Category.actions must apply the same visibility rule as planActions, on both resolver paths."""

    @pytest.fixture
    def actions(self, plan):
        category = CategoryFactory.create(type=CategoryTypeFactory.create(plan=plan), external_identifier='cat')
        public = ActionFactory.create(
            plan=plan, categories=[category], visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC
        )
        internal = ActionFactory.create(
            plan=plan, categories=[category], visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL
        )
        return category, public, internal

    def _query(self, graphql_client_query, plan, category, prefetched: bool) -> set[str]:
        if prefetched:
            response = graphql_client_query(PLAN_CATEGORIES_QUERY, variables={'plan': plan.identifier})
            assert 'errors' not in response, json.dumps(response)
            [category_data] = response['data']['planCategories']
        else:
            response = graphql_client_query(
                CATEGORY_QUERY,
                variables={
                    'plan': plan.identifier,
                    'categoryType': category.type.identifier,
                    'category': category.external_identifier,
                },
            )
            assert 'errors' not in response, json.dumps(response)
            category_data = response['data']['category']
        return {action['identifier'] for action in category_data['actions']}

    @pytest.mark.parametrize('prefetched', [True, False])
    def test_anonymous_user_sees_only_public_actions(self, plan, actions, graphql_client_query, prefetched):
        category, public, _internal = actions

        assert self._query(graphql_client_query, plan, category, prefetched) == {public.identifier}

    @pytest.mark.parametrize('prefetched', [True, False])
    def test_plan_staff_see_internal_actions(self, plan, actions, client, plan_admin_user, graphql_client_query, prefetched):
        category, public, internal = actions
        client.force_login(plan_admin_user)

        assert self._query(graphql_client_query, plan, category, prefetched) == {public.identifier, internal.identifier}
