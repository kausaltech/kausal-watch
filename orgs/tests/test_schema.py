from datetime import timedelta

from django.utils import timezone

import pytest

from actions.tests.factories import PlanFactory
from orgs.tests.factories import OrganizationFactory

pytestmark = pytest.mark.django_db

ORGANIZATION_QUERY = """
    query($id: ID!) {
      organization(id: $id) {
        id
      }
    }
"""


@pytest.mark.parametrize(
    'published_at',
    [
        timezone.now() - timedelta(days=1),  # Published
        None,  # Unpublished
    ],
)
def test_resolve_plans_with_action_responsibilities_visibility(
    graphql_client_query_data,
    organization,
    published_at,
):
    """Test plan visibility for unauthenticated users based on publication status."""
    plan = PlanFactory.create(published_at=published_at)
    plan.related_organizations.add(organization)
    organization.responsible_for_actions.create(plan=plan)

    response = graphql_client_query_data(
        """
        query($id: ID!) {
          organization(id: $id) {
            plansWithActionResponsibilities {
              id
            }
          }
        }
        """,
        variables={'id': str(organization.id)},
        headers={'X-Cache-Plan-Identifier': plan.identifier},
    )

    expected = {
        'organization': {
            'plansWithActionResponsibilities': [
                {
                    'id': plan.identifier,
                }
            ]
            if published_at is not None
            else []
        }
    }

    assert response == expected


def test_resolve_organization_blocks_other_plans_orgs(graphql_client_query_data):
    """An org from one plan must not be returned when queried from another plan's context."""
    plan_a = PlanFactory.create()
    plan_b = PlanFactory.create()
    org_a = OrganizationFactory.create()
    plan_a.related_organizations.add(org_a)

    response = graphql_client_query_data(
        ORGANIZATION_QUERY,
        variables={'id': str(org_a.id)},
        headers={'X-Cache-Plan-Identifier': plan_b.identifier},
    )
    assert response == {'organization': None}


def test_resolve_organization_returns_none_without_plan_context(graphql_client_query_data, organization):
    """Without a plan context (no header / directive), no organization should be returned."""
    response = graphql_client_query_data(
        ORGANIZATION_QUERY,
        variables={'id': str(organization.id)},
    )
    assert response == {'organization': None}


def test_resolve_organization_returns_org_in_current_plan(graphql_client_query_data):
    """Within the current plan's context, its own organizations must still resolve."""
    plan = PlanFactory.create()
    org = OrganizationFactory.create()
    plan.related_organizations.add(org)

    response = graphql_client_query_data(
        ORGANIZATION_QUERY,
        variables={'id': str(org.id)},
        headers={'X-Cache-Plan-Identifier': plan.identifier},
    )
    assert response == {'organization': {'id': str(org.id)}}
