"""
Tests for Plan GraphQL queries with is_active field.

This module tests that inactive plans are properly filtered in GraphQL queries
based on user permissions.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

import pytest

from actions.models.plan import PublicationStatus

pytestmark = pytest.mark.django_db


PLAN_QUERY = """
    query GetPlan($id: ID!) {
        plan(id: $id) {
            id
            identifier
            name
        }
    }
"""

PLAN_WITH_IS_ACTIVE_QUERY = """
    query GetPlan($id: ID!) {
        plan(id: $id) {
            id
            identifier
            name
            isActive
        }
    }
"""

PLANS_FOR_HOSTNAME_QUERY = """
    query GetPlansForHostname($hostname: String) {
        plansForHostname(hostname: $hostname) {
            __typename
            ... on Plan {
                id
                identifier
                name
            }
        }
    }
"""

WORKFLOW_STATES_QUERY = """
    query GetWorkflowStates($plan: ID!) {
        workflowStates(plan: $plan) {
            id
        }
    }
"""

PUBLIC_PLAN_WORKFLOW_STATES_QUERY = """
    query GetPublicPlanWorkflowStates($hostname: String, $plan: ID!) {
        plansForHostname(hostname: $hostname) {
            __typename
        }
        workflowStates(plan: $plan) {
            id
        }
    }
"""


class TestPlanGraphQLIsActive:
    """Test GraphQL queries respect is_active field."""

    def test_anonymous_cannot_query_inactive_plan_by_id(self, graphql_client_query_data, plan_factory):
        """Test that anonymous users cannot query inactive plans by ID."""
        inactive_plan = plan_factory(
            is_active=False,
            published_at=timezone.now() - timedelta(days=1),
        )

        data = graphql_client_query_data(
            PLAN_QUERY,
            variables={'id': inactive_plan.identifier},
        )

        # Should return None for inactive plan
        assert data['plan'] is None

    def test_superuser_cannot_query_inactive_plan_by_id(self, client, graphql_client_query_data, plan_factory, user_factory):
        inactive_plan = plan_factory(
            is_active=False,
            published_at=timezone.now() - timedelta(days=1),
        )
        client.force_login(user_factory(is_superuser=True))

        data = graphql_client_query_data(
            PLAN_QUERY,
            variables={'id': inactive_plan.identifier},
        )

        assert data['plan'] is None

    def test_superuser_cannot_query_inactive_plan_workflow_states(
        self, client, graphql_client_query_data, plan_factory, user_factory
    ):
        inactive_plan = plan_factory(is_active=False)
        client.force_login(user_factory(is_superuser=True))

        data = graphql_client_query_data(
            WORKFLOW_STATES_QUERY,
            variables={'plan': inactive_plan.identifier},
        )

        assert data['workflowStates'] == []

    def test_anonymous_can_query_workflow_states_for_plan_published_by_domain_override(
        self,
        graphql_client_query_data,
        plan_domain_factory,
        plan_factory,
        workflow_factory,
        workflow_task_factory,
    ):
        plan = plan_factory(published_at=None)
        plan.features.expose_unpublished_plan_only_to_authenticated_user = True
        workflow = workflow_factory()
        workflow_task_factory(workflow=workflow)
        plan.features.moderation_workflow = workflow
        plan.features.save()
        domain = plan_domain_factory(
            plan=plan,
            publication_status_override=PublicationStatus.PUBLISHED,
        )

        data = graphql_client_query_data(
            PUBLIC_PLAN_WORKFLOW_STATES_QUERY,
            variables={'hostname': domain.hostname, 'plan': plan.identifier},
        )

        assert data['plansForHostname'][0]['__typename'] == 'Plan'
        assert data['workflowStates'] == [{'id': 'PUBLISHED'}]

    def test_anonymous_can_query_active_plan_by_id(self, graphql_client_query_data, plan_factory):
        """Test that anonymous users can query active published plans by ID."""
        active_plan = plan_factory(
            is_active=True,
            published_at=timezone.now() - timedelta(days=1),
        )
        # Ensure expose flag allows viewing
        active_plan.features.expose_unpublished_plan_only_to_authenticated_user = False
        active_plan.features.save()

        data = graphql_client_query_data(
            PLAN_QUERY,
            variables={'id': active_plan.identifier},
        )

        assert data['plan'] is not None
        assert data['plan']['identifier'] == active_plan.identifier


class TestPlansForHostnameGraphQL:
    """Test plansForHostname GraphQL query respects is_active field."""

    @pytest.mark.parametrize('user_kind', ['anonymous', 'superuser'])
    @pytest.mark.parametrize('publication_override', [None, 'PUBLISHED'])
    def test_plans_for_hostname_excludes_inactive_plan(
        self,
        client,
        graphql_client_query_data,
        plan_factory,
        plan_domain_factory,
        user_factory,
        user_kind,
        publication_override,
    ):
        inactive_plan = plan_factory(
            is_active=False,
            published_at=timezone.now() - timedelta(days=1),
        )
        inactive_domain = plan_domain_factory(
            plan=inactive_plan,
            hostname='inactive.example.com',
            publication_status_override=publication_override,
        )
        inactive_plan.features.expose_unpublished_plan_only_to_authenticated_user = False
        inactive_plan.features.save()

        if user_kind == 'superuser':
            client.force_login(user_factory(is_superuser=True))

        data = graphql_client_query_data(
            PLANS_FOR_HOSTNAME_QUERY,
            variables={'hostname': inactive_domain.hostname},
        )

        assert data['plansForHostname'] == []

    def test_plans_for_hostname_returns_active_plan(self, graphql_client_query_data, plan_factory, plan_domain_factory):
        active_plan = plan_factory(
            is_active=True,
            published_at=timezone.now() - timedelta(days=1),
        )
        active_domain = plan_domain_factory(plan=active_plan, hostname='active.example.com')

        data = graphql_client_query_data(
            PLANS_FOR_HOSTNAME_QUERY,
            variables={'hostname': active_domain.hostname},
        )

        assert data['plansForHostname'][0]['identifier'] == active_plan.identifier


class TestPlanIsActiveFieldInSchema:
    """Test that isActive field is exposed in GraphQL schema."""

    def test_is_active_field_in_plan_type(self, graphql_client_query_data, plan_factory):
        """Test that isActive field is available on Plan type."""
        active_plan = plan_factory(
            is_active=True,
            published_at=timezone.now() - timedelta(days=1),
        )
        active_plan.features.expose_unpublished_plan_only_to_authenticated_user = False
        active_plan.features.save()

        data = graphql_client_query_data(
            PLAN_WITH_IS_ACTIVE_QUERY,
            variables={'id': active_plan.identifier},
        )

        assert data['plan'] is not None
        # The field should be present in the response
        assert 'isActive' in data['plan']
        assert data['plan']['isActive'] is True
