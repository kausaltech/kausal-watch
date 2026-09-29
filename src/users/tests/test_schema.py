from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from actions.tests.factories import PlanFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

if TYPE_CHECKING:
    from actions.models import Plan
    from users.models import User

pytestmark = pytest.mark.django_db

ME_QUERY = """
    query($plan: ID!) {
        me {
            canAccessAdmin(plan: $plan)
        }
    }
"""


def test_me_is_null_for_anonymous_user(plan: Plan, graphql_client_query_data):
    data = graphql_client_query_data(ME_QUERY, variables={'plan': plan.identifier})
    assert data['me'] is None


def test_plan_admin_can_access_admin_of_their_plan(client, plan_admin_user: User, plan: Plan, graphql_client_query_data):
    client.force_login(plan_admin_user)
    data = graphql_client_query_data(ME_QUERY, variables={'plan': plan.identifier})
    assert data['me']['canAccessAdmin'] is True


def test_plan_admin_cannot_access_admin_of_other_plan(client, plan_admin_user: User, graphql_client_query_data):
    other_plan = PlanFactory.create()
    client.force_login(plan_admin_user)
    data = graphql_client_query_data(ME_QUERY, variables={'plan': other_plan.identifier})
    assert data['me']['canAccessAdmin'] is False


def test_plan_can_be_given_by_id(client, plan_admin_user: User, plan: Plan, graphql_client_query_data):
    client.force_login(plan_admin_user)
    data = graphql_client_query_data(ME_QUERY, variables={'plan': str(plan.pk)})
    assert data['me']['canAccessAdmin'] is True


def test_user_without_admin_rights_cannot_access_admin(client, plan: Plan, graphql_client_query_data):
    user = UserFactory.create()
    PersonFactory.create(user=user, organization=plan.organization)
    client.force_login(user)
    data = graphql_client_query_data(ME_QUERY, variables={'plan': plan.identifier})
    assert data['me']['canAccessAdmin'] is False


def test_superuser_can_access_admin_of_any_plan(client, superuser: User, plan: Plan, graphql_client_query_data):
    client.force_login(superuser)
    data = graphql_client_query_data(ME_QUERY, variables={'plan': plan.identifier})
    assert data['me']['canAccessAdmin'] is True


def test_unknown_plan_gives_false(client, superuser: User, graphql_client_query_data):
    client.force_login(superuser)
    data = graphql_client_query_data(ME_QUERY, variables={'plan': 'no-such-plan'})
    assert data['me']['canAccessAdmin'] is False
