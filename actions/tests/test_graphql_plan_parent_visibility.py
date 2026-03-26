"""
Tests that unpublished parent plans are not exposed to public child plans.

When an umbrella (parent) plan is internal/unpublished but some of its child
plans are public, the GraphQL API should not return the parent in `parent` or
`allRelatedPlans` for the published children.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

import pytest

pytestmark = pytest.mark.django_db

PARENT_QUERY = """
    query GetPlan($id: ID!) {
        plan(id: $id) {
            id
            parent {
                id
                identifier
            }
        }
    }
"""

RELATED_PLANS_QUERY = """
    query GetPlan($id: ID!) {
        plan(id: $id) {
            id
            allRelatedPlans {
                id
                identifier
            }
        }
    }
"""

CHILDREN_QUERY = """
    query GetPlan($id: ID!) {
        plan(id: $id) {
            id
            children {
                id
                identifier
            }
        }
    }
"""


def _make_published_plan(plan_factory, **kwargs):
    plan = plan_factory(
        published_at=timezone.now() - timedelta(days=1),
        **kwargs,
    )
    plan.features.expose_unpublished_plan_only_to_authenticated_user = False
    plan.features.save()
    return plan


def _make_unpublished_plan(plan_factory, **kwargs):
    plan = plan_factory(
        published_at=None,
        **kwargs,
    )
    plan.features.expose_unpublished_plan_only_to_authenticated_user = True
    plan.features.save()
    return plan


class TestParentPlanVisibility:
    """Test that unpublished parent plans are hidden from public child plans."""

    def test_published_child_hides_unpublished_parent(self, graphql_client_query_data, plan_factory):
        """Anonymous user querying a published child should not see the unpublished parent."""
        parent = _make_unpublished_plan(plan_factory)
        child = _make_published_plan(plan_factory, parent=parent)

        data = graphql_client_query_data(
            PARENT_QUERY,
            variables={'id': child.identifier},
        )

        assert data['plan'] is not None
        assert data['plan']['parent'] is None

    def test_published_child_shows_published_parent(self, graphql_client_query_data, plan_factory):
        """Anonymous user querying a published child should see a published parent."""
        parent = _make_published_plan(plan_factory)
        child = _make_published_plan(plan_factory, parent=parent)

        data = graphql_client_query_data(
            PARENT_QUERY,
            variables={'id': child.identifier},
        )

        assert data['plan'] is not None
        assert data['plan']['parent'] is not None
        assert data['plan']['parent']['identifier'] == parent.identifier


class TestAllRelatedPlansVisibility:
    """Test that allRelatedPlans excludes unpublished plans."""

    def test_published_child_excludes_unpublished_parent_from_related(self, graphql_client_query_data, plan_factory):
        """AllRelatedPlans for a published child should not include the unpublished parent."""
        parent = _make_unpublished_plan(plan_factory)
        child = _make_published_plan(plan_factory, parent=parent)

        data = graphql_client_query_data(
            RELATED_PLANS_QUERY,
            variables={'id': child.identifier},
        )

        assert data['plan'] is not None
        related_identifiers = [p['identifier'] for p in data['plan']['allRelatedPlans']]
        assert parent.identifier not in related_identifiers

    def test_published_child_excludes_unpublished_sibling_from_related(self, graphql_client_query_data, plan_factory):
        """AllRelatedPlans should not include unpublished siblings."""
        parent = _make_unpublished_plan(plan_factory)
        child_public = _make_published_plan(plan_factory, parent=parent)
        child_internal = _make_unpublished_plan(plan_factory, parent=parent)

        data = graphql_client_query_data(
            RELATED_PLANS_QUERY,
            variables={'id': child_public.identifier},
        )

        assert data['plan'] is not None
        related_identifiers = [p['identifier'] for p in data['plan']['allRelatedPlans']]
        assert parent.identifier not in related_identifiers
        assert child_internal.identifier not in related_identifiers

    def test_published_child_includes_published_sibling_in_related(self, graphql_client_query_data, plan_factory):
        """AllRelatedPlans should include published siblings."""
        parent = _make_unpublished_plan(plan_factory)
        child1 = _make_published_plan(plan_factory, parent=parent)
        child2 = _make_published_plan(plan_factory, parent=parent)

        data = graphql_client_query_data(
            RELATED_PLANS_QUERY,
            variables={'id': child1.identifier},
        )

        assert data['plan'] is not None
        related_identifiers = [p['identifier'] for p in data['plan']['allRelatedPlans']]
        assert child2.identifier in related_identifiers
        assert parent.identifier not in related_identifiers


class TestChildrenVisibility:
    """Test that children field filters out plans not visible to user."""

    def test_children_excludes_invisible_children(self, graphql_client_query_data, plan_factory):
        """Children should only include plans visible to the requesting user."""
        parent = _make_published_plan(plan_factory)
        child_public = _make_published_plan(plan_factory, parent=parent)
        child_internal = _make_unpublished_plan(plan_factory, parent=parent)

        data = graphql_client_query_data(
            CHILDREN_QUERY,
            variables={'id': parent.identifier},
        )

        assert data['plan'] is not None
        child_identifiers = [c['identifier'] for c in data['plan']['children']]
        assert child_public.identifier in child_identifiers
        assert child_internal.identifier not in child_identifiers
