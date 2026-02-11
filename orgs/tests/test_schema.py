from datetime import timedelta

from django.utils import timezone

import pytest

from actions.tests.factories import PlanFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    'published_at',
    [
        timezone.now() - timedelta(days=1),  # Published
        None,  # Unpublished
    ]
)
def test_resolve_plans_with_action_responsibilities_visibility(
    graphql_client_query_data,
    organization,
    published_at,
):
    """Test plan visibility for unauthenticated users based on publication status."""
    plan = PlanFactory(published_at=published_at)
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
    )

    expected = {
        'organization': {
            'plansWithActionResponsibilities': [{
                'id': plan.identifier,
            }] if published_at is not None else []
        }
    }

    assert response == expected
