from __future__ import annotations

from django.core.exceptions import ValidationError

import pytest

from actions.models import PublicUser
from actions.tests.factories import PlanFactory
from actions.tests.test_graphql_pledge import SIGN_IN_MUTATION, SIGN_UP_MUTATION, VERIFY_PIN_MUTATION
from admin_site.tests.factories import ClientFactory

pytestmark = pytest.mark.django_db


PLAN_FEATURES_ACCOUNTS_QUERY = """
    query($plan: ID!) {
        plan(id: $plan) {
            features {
                enableCommunityEngagementAccounts
            }
        }
    }
"""

REGISTER_USER_MUTATION = """
    mutation {
      pledge {
        registerUser {
          uuid
        }
      }
    }
"""

PUBLIC_USER_QUERY = """
    query {
      publicUser {
        email
      }
    }
"""


def _create_engagement_plan(*, accounts: bool):
    plan = PlanFactory.create(primary_client=ClientFactory.create())
    plan.features.enable_community_engagement = True
    plan.features.enable_community_engagement_accounts = accounts
    plan.features.save()
    return plan


class TestAccountsFeature:
    def test_accounts_are_off_by_default(self):
        plan = PlanFactory.create()

        assert plan.features.enable_community_engagement_accounts is False

    def test_exposed_in_graphql(self, graphql_client_query_data):
        plan = _create_engagement_plan(accounts=True)

        data = graphql_client_query_data(PLAN_FEATURES_ACCOUNTS_QUERY, variables={'plan': plan.identifier})

        assert data['plan']['features']['enableCommunityEngagementAccounts'] is True

    def test_accounts_require_community_engagement(self):
        plan = PlanFactory.create(primary_client=ClientFactory.create())
        plan.features.enable_community_engagement_accounts = True

        with pytest.raises(ValidationError) as exc_info:
            plan.features.full_clean()

        assert 'enable_community_engagement_accounts' in exc_info.value.message_dict


class TestAccountMutationsWhenAccountsAreOff:
    @pytest.fixture(autouse=True)
    def setup(self):
        # graphql_client_query sends X-Cache-Plan-Identifier from self.plan
        self.plan = _create_engagement_plan(accounts=False)

    def test_sign_up_is_refused(self, graphql_client_query):
        response = graphql_client_query(
            SIGN_UP_MUTATION,
            variables={'email': 'new@example.com', 'terms': True, 'marketing': False},
        )

        assert response['errors'][0]['extensions']['code'] == 'ACCOUNTS_DISABLED'

    def test_sign_in_is_refused(self, graphql_client_query):
        PublicUser.objects.create(email='alice@example.com', client=self.plan.primary_client)

        response = graphql_client_query(SIGN_IN_MUTATION, variables={'email': 'alice@example.com'})

        assert response['errors'][0]['extensions']['code'] == 'ACCOUNTS_DISABLED'

    def test_verify_pin_is_refused(self, graphql_client_query):
        response = graphql_client_query(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': '123456'},
        )

        assert response['errors'][0]['extensions']['code'] == 'ACCOUNTS_DISABLED'

    def test_anonymous_registration_still_works(self, graphql_client_query_data):
        data = graphql_client_query_data(REGISTER_USER_MUTATION)

        assert data['pledge']['registerUser']['uuid']

    def test_existing_token_still_resolves(self, graphql_client_query_data):
        public_user = PublicUser.objects.create(email='alice@example.com', client=self.plan.primary_client)
        token = public_user.regenerate_user_token()

        data = graphql_client_query_data(PUBLIC_USER_QUERY, headers={'X-Public-User-Token': token})

        assert data['publicUser']['email'] == 'alice@example.com'


class TestAccountMutationsWhenAccountsAreOn:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = _create_engagement_plan(accounts=True)

    def test_sign_up_sends_a_code(self, graphql_client_query_data):
        data = graphql_client_query_data(
            SIGN_UP_MUTATION,
            variables={'email': 'new@example.com', 'terms': True, 'marketing': False},
        )

        assert data['pledge']['signUp']['sent'] is True
