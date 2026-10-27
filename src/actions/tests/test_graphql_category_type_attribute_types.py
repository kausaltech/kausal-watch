"""
Tests for which attribute type definitions `CategoryType.attributeTypes` shows.

The values of an attribute type that a user may not see are already filtered out of `attributes`. The
definitions (name, help text, choice options, ...) must be filtered the same way, or they tell an anonymous
visitor what the internal fields are.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest

from aplans.utils import InstancesVisibleForMixin

from actions.tests.factories import AttributeRichTextFactory, AttributeTypeFactory, CategoryFactory, CategoryTypeFactory

if TYPE_CHECKING:
    from actions.models import AttributeType, CategoryType

pytestmark = pytest.mark.django_db

VisibleFor = InstancesVisibleForMixin.VisibleFor

CATEGORY_TYPES_QUERY = """
query($plan: ID!) {
  plan(id: $plan) {
    categoryTypes {
      identifier
      attributeTypes {
        identifier
      }
      categories {
        attributes {
          type {
            identifier
          }
        }
      }
    }
  }
}
"""

LEVELS = [VisibleFor.PUBLIC, VisibleFor.AUTHENTICATED, VisibleFor.PLAN_ADMINS]


@pytest.fixture
def category_type(plan) -> CategoryType:
    return CategoryTypeFactory.create(plan=plan)


@pytest.fixture
def attribute_types(category_type) -> dict[InstancesVisibleForMixin.VisibleFor, AttributeType]:
    """Create one attribute type per visibility level, each with a value on one category."""
    category = CategoryFactory.create(type=category_type)
    result = {}
    for level in LEVELS:
        attribute_type = AttributeTypeFactory.create(scope=category_type, instances_visible_for=level)
        AttributeRichTextFactory.create(type=attribute_type, content_object=category)
        result[level] = attribute_type
    return result


@pytest.fixture
def person_user(person):
    return person.user


def query_category_type(graphql_client_query_data, plan, category_type) -> dict:
    data = graphql_client_query_data(CATEGORY_TYPES_QUERY, variables={'plan': plan.identifier})
    [category_type_data] = [ct for ct in data['plan']['categoryTypes'] if ct['identifier'] == category_type.identifier]
    return category_type_data


def attribute_type_identifiers(category_type_data: dict) -> list[str]:
    return [at['identifier'] for at in category_type_data['attributeTypes']]


def attribute_value_type_identifiers(category_type_data: dict) -> set[str]:
    return {attr['type']['identifier'] for cat in category_type_data['categories'] for attr in cat['attributes']}


@pytest.mark.parametrize(
    ('user_fixture', 'visible_levels'),
    [
        (None, [VisibleFor.PUBLIC]),
        # `person_user` has a person but no role in the plan; the API rejects users without a person
        ('person_user', [VisibleFor.PUBLIC, VisibleFor.AUTHENTICATED]),
        ('plan_admin_user', LEVELS),
        ('superuser', LEVELS),
    ],
    ids=['anonymous', 'authenticated', 'plan_admin', 'superuser'],
)
def test_attribute_types_are_filtered_by_visibility(
    request, client, graphql_client_query_data, plan, category_type, attribute_types, user_fixture, visible_levels
):
    if user_fixture is not None:
        client.force_login(request.getfixturevalue(user_fixture))

    data = query_category_type(graphql_client_query_data, plan, category_type)

    expected = [attribute_types[level].identifier for level in visible_levels]
    assert attribute_type_identifiers(data) == expected
    # The attribute values of the same category type are filtered the same way, so every value has its type
    assert attribute_value_type_identifiers(data) == set(expected)


def test_attribute_types_are_ordered_by_pk(client, graphql_client_query_data, plan, category_type, plan_admin_user):
    # Create in an order where identifiers and pks disagree, so ordering by identifier would fail
    created = [
        AttributeTypeFactory.create(scope=category_type, identifier=identifier, instances_visible_for=level)
        for identifier, level in [
            ('c', VisibleFor.PUBLIC),
            ('b', VisibleFor.PLAN_ADMINS),
            ('a', VisibleFor.AUTHENTICATED),
            ('d', VisibleFor.PUBLIC),
        ]
    ]
    client.force_login(plan_admin_user)

    data = query_category_type(graphql_client_query_data, plan, category_type)

    assert attribute_type_identifiers(data) == [at.identifier for at in sorted(created, key=lambda at: at.pk)]


def test_query_count_does_not_grow_with_attribute_types(client, graphql_client_query_data, plan, plan_admin_user):
    category_type = CategoryTypeFactory.create(plan=plan)
    client.force_login(plan_admin_user)

    def count_queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            graphql_client_query_data(CATEGORY_TYPES_QUERY, variables={'plan': plan.identifier})
        return len(ctx.captured_queries)

    AttributeTypeFactory.create(scope=category_type, instances_visible_for=VisibleFor.PLAN_ADMINS)
    count_queries()  # warm up per-request caches that are not specific to this resolver
    queries_for_one = count_queries()
    for level in LEVELS:
        AttributeTypeFactory.create(scope=category_type, instances_visible_for=level)
    assert count_queries() == queries_for_one


def test_plan_is_not_queried_per_category(graphql_client_query_data, plan, category_type):
    # On `planCategories { type }`, every category has its own instance of its category type
    query = 'query($plan: ID!) { planCategories(plan: $plan) { type { attributeTypes { identifier } } } }'
    AttributeTypeFactory.create(scope=category_type)

    def count_plan_queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            graphql_client_query_data(query, variables={'plan': plan.identifier})
        return sum('FROM "actions_plan"' in q['sql'] for q in ctx.captured_queries)

    CategoryFactory.create(type=category_type)
    plan_queries_for_one = count_plan_queries()
    for _ in range(3):
        CategoryFactory.create(type=category_type)
    assert count_plan_queries() == plan_queries_for_one
