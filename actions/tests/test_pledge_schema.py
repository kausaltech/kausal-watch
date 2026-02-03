from __future__ import annotations

import uuid

import pytest

from actions.models import Pledge, PledgeCommitment, PledgeUser
from actions.tests.factories import PlanFactory

pytestmark = pytest.mark.django_db


class TestRegisterPledgeUserMutation:
    """Tests for the registerUser GraphQL mutation."""

    def test_register_user_creates_pledge_user(self, graphql_client_query_data):
        """Test that the mutation creates a PledgeUser in the database."""
        initial_count = PledgeUser.objects.count()

        data = graphql_client_query_data(
            """
            mutation {
              pledge {
                registerUser {
                  uuid
                }
              }
            }
            """
        )

        assert PledgeUser.objects.count() == initial_count + 1

        # Verify the returned UUID matches the created user
        returned_uuid = data['pledge']['registerUser']['uuid']
        pledge_user = PledgeUser.objects.get(uuid=returned_uuid)
        assert pledge_user is not None
        assert pledge_user.user_data == {}

    def test_register_user_creates_unique_users(self, graphql_client_query_data):
        """Test that multiple calls create different users."""
        data1 = graphql_client_query_data(
            """
            mutation {
              pledge {
                registerUser {
                  uuid
                }
              }
            }
            """
        )

        data2 = graphql_client_query_data(
            """
            mutation {
              pledge {
                registerUser {
                  uuid
                }
              }
            }
            """
        )

        uuid1 = data1['pledge']['registerUser']['uuid']
        uuid2 = data2['pledge']['registerUser']['uuid']

        assert uuid1 != uuid2
        assert PledgeUser.objects.count() == 2


class TestCommitToPledgeMutation:
    """Tests for the commitToPledge GraphQL mutation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()
        self.pledge = Pledge.objects.create(
            plan=self.plan,
            name='Test Pledge',
            slug='test-pledge',
        )
        self.pledge_user = PledgeUser.objects.create()

    def test_commit_to_pledge_creates_commitment(self, graphql_client_query_data):
        """Test that committing creates a PledgeCommitment."""
        assert PledgeCommitment.objects.count() == 0

        data = graphql_client_query_data(
            """
            mutation($userId: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userId: $userId, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userId': str(self.pledge_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': True,
            },
        )

        assert data['pledge']['commitToPledge']['committed'] is True
        assert PledgeCommitment.objects.count() == 1

        commitment = PledgeCommitment.objects.first()
        assert commitment is not None
        assert commitment.pledge == self.pledge
        assert commitment.pledge_user == self.pledge_user

    def test_uncommit_from_pledge_removes_commitment(self, graphql_client_query_data):
        """Test that uncommitting removes the PledgeCommitment."""
        # Create a commitment first
        PledgeCommitment.objects.create(
            pledge=self.pledge,
            pledge_user=self.pledge_user,
        )
        assert PledgeCommitment.objects.count() == 1

        data = graphql_client_query_data(
            """
            mutation($userId: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userId: $userId, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userId': str(self.pledge_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': False,
            },
        )

        assert data['pledge']['commitToPledge']['committed'] is False
        assert PledgeCommitment.objects.count() == 0

    def test_commit_when_already_committed_is_idempotent(self, graphql_client_query_data):
        """Test that committing twice doesn't create duplicate commitments."""
        # Create a commitment first
        PledgeCommitment.objects.create(
            pledge=self.pledge,
            pledge_user=self.pledge_user,
        )
        assert PledgeCommitment.objects.count() == 1

        data = graphql_client_query_data(
            """
            mutation($userId: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userId: $userId, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userId': str(self.pledge_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': True,
            },
        )

        assert data['pledge']['commitToPledge']['committed'] is True
        assert PledgeCommitment.objects.count() == 1

    def test_uncommit_when_not_committed_is_idempotent(self, graphql_client_query_data):
        """Test that uncommitting when not committed doesn't error."""
        assert PledgeCommitment.objects.count() == 0

        data = graphql_client_query_data(
            """
            mutation($userId: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userId: $userId, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userId': str(self.pledge_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': False,
            },
        )

        assert data['pledge']['commitToPledge']['committed'] is False
        assert PledgeCommitment.objects.count() == 0

    def test_commit_with_invalid_user_id_returns_error(self, graphql_client_query):
        """Test that committing with invalid user ID returns an error."""
        fake_uuid = str(uuid.uuid4())

        response = graphql_client_query(
            """
            mutation($userId: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userId: $userId, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userId': fake_uuid,
                'pledgeId': str(self.pledge.id),
                'committed': True,
            },
        )

        assert 'errors' in response
        assert 'PledgeUser not found' in response['errors'][0]['message']

    def test_commit_with_invalid_pledge_id_returns_error(self, graphql_client_query):
        """Test that committing with invalid pledge ID returns an error."""
        response = graphql_client_query(
            """
            mutation($userId: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userId: $userId, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userId': str(self.pledge_user.uuid),
                'pledgeId': '99999',
                'committed': True,
            },
        )

        assert 'errors' in response
        assert 'Pledge not found' in response['errors'][0]['message']

    def test_commit_when_community_engagement_disabled_returns_error(self, graphql_client_query):
        """Test that committing fails when community engagement is disabled for the plan."""
        self.plan.features.enable_community_engagement = False
        self.plan.features.save()

        response = graphql_client_query(
            """
            mutation($userId: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userId: $userId, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userId': str(self.pledge_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': True,
            },
        )

        assert 'errors' in response
        assert 'Community engagement is not enabled for this plan' in response['errors'][0]['message']
        assert PledgeCommitment.objects.count() == 0
