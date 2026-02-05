from __future__ import annotations

import uuid

import pytest

from actions.models import Pledge, PledgeCommitment, PledgeUser
from actions.tests.factories import ActionFactory, PlanFactory, PledgeFactory
from images.tests.factories import AplansImageFactory

pytestmark = pytest.mark.django_db


PLEDGE_FIELDS = """
    id
    uuid
    name
    slug
    description
    residentCount
    impactStatement
    localEquivalency
    order
    commitmentCount
"""

# Pledges are nested under plan
PLEDGE_QUERY = f"""
    query($plan: ID!, $id: ID, $slug: String) {{
        plan(id: $plan) {{
            pledge(id: $id, slug: $slug) {{
                {PLEDGE_FIELDS}
            }}
        }}
    }}
"""

PLEDGES_QUERY = f"""
    query($plan: ID!) {{
        plan(id: $plan) {{
            pledges {{
                {PLEDGE_FIELDS}
            }}
        }}
    }}
"""

PLEDGE_WITH_ACTIONS_QUERY = """
    query($plan: ID!, $id: ID) {
        plan(id: $plan) {
            pledge(id: $id) {
                id
                name
                actions {
                    id
                    identifier
                    name
                }
            }
        }
    }
"""

PLEDGE_WITH_IMAGE_QUERY = """
    query($plan: ID!, $id: ID) {
        plan(id: $plan) {
            pledge(id: $id) {
                id
                name
                image {
                    id
                }
            }
        }
    }
"""

PLAN_FEATURES_QUERY = """
    query($plan: ID!) {
        plan(id: $plan) {
            features {
                enableCommunityEngagement
            }
        }
    }
"""


class TestPledgeQueryById:
    @pytest.fixture(autouse=True)
    def setup(self):
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()
        self.plan = plan

    def test_pledge_query_by_id_returns_pledge(self, graphql_client_query_data):
        """Test that pledge query returns pledge when queried by ID."""
        pledge = PledgeFactory.create(plan=self.plan)

        data = graphql_client_query_data(
            PLEDGE_QUERY,
            variables={'plan': self.plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is not None
        assert data['plan']['pledge']['id'] == str(pledge.id)
        assert data['plan']['pledge']['name'] == pledge.name
        assert data['plan']['pledge']['slug'] == pledge.slug

    def test_pledge_query_by_slug_returns_pledge(self, graphql_client_query_data):
        """Test that pledge query returns pledge when queried by slug."""
        pledge = PledgeFactory.create(plan=self.plan, slug='test-slug')

        data = graphql_client_query_data(
            PLEDGE_QUERY,
            variables={'plan': self.plan.identifier, 'slug': 'test-slug'},
        )

        assert data['plan']['pledge'] is not None
        assert data['plan']['pledge']['slug'] == 'test-slug'
        assert data['plan']['pledge']['name'] == pledge.name

    def test_pledge_query_returns_null_when_not_found(self, graphql_client_query_data):
        """Test that pledge query returns null for non-existent ID."""
        data = graphql_client_query_data(
            PLEDGE_QUERY,
            variables={'plan': self.plan.identifier, 'id': '99999'},
        )

        assert data['plan']['pledge'] is None

    def test_pledge_query_returns_null_for_nonexistent_slug(self, graphql_client_query_data):
        """Test that pledge query returns null for non-existent slug."""
        data = graphql_client_query_data(
            PLEDGE_QUERY,
            variables={'plan': self.plan.identifier, 'slug': 'nonexistent-slug'},
        )

        assert data['plan']['pledge'] is None

    def test_pledge_query_returns_all_fields(self, graphql_client_query_data):
        """Test that pledge query returns all exposed fields correctly."""
        pledge = PledgeFactory.create(
            plan=self.plan,
            name='Test Pledge',
            slug='test-pledge',
            description='Test description',
            resident_count=150,
            impact_statement='We save 150kg CO₂e',
            local_equivalency="That's equivalent to 15 trips",
            order=5,
        )

        data = graphql_client_query_data(
            PLEDGE_QUERY,
            variables={'plan': self.plan.identifier, 'id': str(pledge.id)},
        )

        result = data['plan']['pledge']
        assert result['name'] == 'Test Pledge'
        assert result['slug'] == 'test-pledge'
        assert result['description'] == 'Test description'
        assert result['residentCount'] == 150
        assert result['impactStatement'] == 'We save 150kg CO₂e'
        assert result['localEquivalency'] == "That's equivalent to 15 trips"
        assert result['order'] == 5
        assert result['uuid'] is not None


class TestPledgeQueryFeatureFlag:
    def test_pledge_query_returns_null_when_feature_disabled(self, graphql_client_query_data):
        """Test that pledge query returns null when enable_community_engagement is False."""
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = False
        plan.features.save()

        pledge = PledgeFactory.create(plan=plan)

        data = graphql_client_query_data(
            PLEDGE_QUERY,
            variables={'plan': plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is None

    def test_pledge_query_returns_pledge_when_feature_enabled(self, graphql_client_query_data):
        """Test that pledge query returns pledge when feature is enabled."""
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()

        pledge = PledgeFactory.create(plan=plan)

        data = graphql_client_query_data(
            PLEDGE_QUERY,
            variables={'plan': plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is not None
        assert data['plan']['pledge']['id'] == str(pledge.id)


class TestPledgesListQuery:
    @pytest.fixture(autouse=True)
    def setup(self):
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()
        self.plan = plan

    def test_pledges_query_returns_all_pledges(self, graphql_client_query_data):
        """Test that pledges query returns all pledges for the plan."""
        pledge1 = PledgeFactory.create(plan=self.plan, order=1)
        pledge2 = PledgeFactory.create(plan=self.plan, order=2)
        pledge3 = PledgeFactory.create(plan=self.plan, order=3)

        data = graphql_client_query_data(
            PLEDGES_QUERY,
            variables={'plan': self.plan.identifier},
        )

        assert data['plan']['pledges'] is not None
        assert len(data['plan']['pledges']) == 3

        ids = [p['id'] for p in data['plan']['pledges']]
        assert str(pledge1.id) in ids
        assert str(pledge2.id) in ids
        assert str(pledge3.id) in ids

    def test_pledges_query_ordered_by_order_field(self, graphql_client_query_data):
        """Test that pledges are returned ordered by the order field."""
        pledge3 = PledgeFactory.create(plan=self.plan, order=3)
        pledge1 = PledgeFactory.create(plan=self.plan, order=1)
        pledge2 = PledgeFactory.create(plan=self.plan, order=2)

        data = graphql_client_query_data(
            PLEDGES_QUERY,
            variables={'plan': self.plan.identifier},
        )

        assert data['plan']['pledges'][0]['id'] == str(pledge1.id)
        assert data['plan']['pledges'][1]['id'] == str(pledge2.id)
        assert data['plan']['pledges'][2]['id'] == str(pledge3.id)

    def test_pledges_query_returns_null_when_feature_disabled(self, graphql_client_query_data):
        """Test that pledges query returns null when feature is disabled."""
        self.plan.features.enable_community_engagement = False
        self.plan.features.save()

        PledgeFactory.create(plan=self.plan)

        data = graphql_client_query_data(
            PLEDGES_QUERY,
            variables={'plan': self.plan.identifier},
        )

        assert data['plan']['pledges'] is None

    def test_pledges_query_returns_empty_list_when_no_pledges(self, graphql_client_query_data):
        """Test that pledges query returns empty list when no pledges exist."""
        data = graphql_client_query_data(
            PLEDGES_QUERY,
            variables={'plan': self.plan.identifier},
        )

        assert data['plan']['pledges'] is not None
        assert data['plan']['pledges'] == []


class TestPledgePlanIsolation:
    def test_pledge_query_returns_null_for_other_plan_pledge(self, graphql_client_query_data):
        """Test that pledge query cannot access pledges from different plans."""
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()

        # Create another plan with a pledge
        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()
        other_pledge = PledgeFactory.create(plan=other_plan)

        # Query using the original plan's context should not find the other plan's pledge
        data = graphql_client_query_data(
            PLEDGE_QUERY,
            variables={'plan': plan.identifier, 'id': str(other_pledge.id)},
        )

        assert data['plan']['pledge'] is None

    def test_pledges_query_only_returns_current_plan_pledges(self, graphql_client_query_data):
        """Test that pledges query only returns pledges for the current plan."""
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()

        # Create pledges for current plan
        pledge1 = PledgeFactory.create(plan=plan, order=1)

        # Create another plan with pledges
        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()
        PledgeFactory.create(plan=other_plan)

        data = graphql_client_query_data(
            PLEDGES_QUERY,
            variables={'plan': plan.identifier},
        )

        assert len(data['plan']['pledges']) == 1
        assert data['plan']['pledges'][0]['id'] == str(pledge1.id)


class TestPledgeActionsResolver:
    @pytest.fixture(autouse=True)
    def setup(self):
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()
        self.plan = plan

    def test_pledge_resolves_actions(self, graphql_client_query_data):
        """Test that pledge actions field returns linked actions."""
        action1 = ActionFactory.create(plan=self.plan)
        action2 = ActionFactory.create(plan=self.plan)

        pledge = PledgeFactory.create(plan=self.plan, actions=[action1, action2])

        data = graphql_client_query_data(
            PLEDGE_WITH_ACTIONS_QUERY,
            variables={'plan': self.plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is not None
        assert len(data['plan']['pledge']['actions']) == 2

        action_ids = [a['id'] for a in data['plan']['pledge']['actions']]
        assert str(action1.id) in action_ids
        assert str(action2.id) in action_ids

    def test_pledge_with_no_actions_returns_empty_list(self, graphql_client_query_data):
        """Test that pledge with no actions returns empty list."""
        pledge = PledgeFactory.create(plan=self.plan)

        data = graphql_client_query_data(
            PLEDGE_WITH_ACTIONS_QUERY,
            variables={'plan': self.plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is not None
        assert data['plan']['pledge']['actions'] == []

    def test_pledge_actions_filtered_by_user_visibility(self, graphql_client_query_data):
        """
        Test that pledge actions are filtered by user visibility.

        Internal actions should not be visible to anonymous users when accessed
        through a pledge, just like when accessed directly through categories.
        This prevents bypassing action visibility restrictions.
        """
        from aplans.utils import RestrictedVisibilityModel

        # Create a public action that should be visible
        public_action = ActionFactory.create(
            plan=self.plan,
            visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC,
        )
        # Create an internal action that should NOT be visible to anonymous users
        internal_action = ActionFactory.create(
            plan=self.plan,
            visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL,
        )

        # Associate both actions with the pledge
        pledge = PledgeFactory.create(
            plan=self.plan,
            actions=[public_action, internal_action],
        )

        # Query as anonymous user (default for graphql_client_query_data)
        data = graphql_client_query_data(
            PLEDGE_WITH_ACTIONS_QUERY,
            variables={'plan': self.plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is not None
        # Only the public action should be returned
        assert len(data['plan']['pledge']['actions']) == 1
        assert data['plan']['pledge']['actions'][0]['id'] == str(public_action.id)


class TestPledgeImageResolver:
    @pytest.fixture(autouse=True)
    def setup(self):
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()
        self.plan = plan

    def test_pledge_resolves_image(self, graphql_client_query_data):
        """Test that pledge image field returns the associated image."""
        image = AplansImageFactory.create()
        pledge = PledgeFactory.create(plan=self.plan, image=image)

        data = graphql_client_query_data(
            PLEDGE_WITH_IMAGE_QUERY,
            variables={'plan': self.plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is not None
        assert data['plan']['pledge']['image'] is not None
        assert data['plan']['pledge']['image']['id'] == str(image.id)

    def test_pledge_with_no_image_returns_null(self, graphql_client_query_data):
        """Test that pledge with no image returns null for image field."""
        pledge = PledgeFactory.create(plan=self.plan, image=None)

        data = graphql_client_query_data(
            PLEDGE_WITH_IMAGE_QUERY,
            variables={'plan': self.plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is not None
        assert data['plan']['pledge']['image'] is None


class TestPledgeCommitmentCount:
    @pytest.fixture(autouse=True)
    def setup(self):
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()
        self.plan = plan

    def test_pledge_with_no_commitments_returns_zero(self, graphql_client_query_data):
        """Test that a pledge with no commitments returns commitmentCount of 0."""
        pledge = PledgeFactory.create(plan=self.plan)

        data = graphql_client_query_data(
            PLEDGE_QUERY,
            variables={'plan': self.plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is not None
        assert data['plan']['pledge']['commitmentCount'] == 0

    def test_pledge_with_commitments_returns_correct_count(self, graphql_client_query_data):
        """Test that a pledge with commitments returns the correct count."""
        pledge = PledgeFactory.create(plan=self.plan)

        # Create multiple pledge users and commitments
        for _ in range(3):
            pledge_user = PledgeUser.objects.create()
            PledgeCommitment.objects.create(pledge=pledge, pledge_user=pledge_user)

        data = graphql_client_query_data(
            PLEDGE_QUERY,
            variables={'plan': self.plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is not None
        assert data['plan']['pledge']['commitmentCount'] == 3

    def test_commitment_count_is_independent_per_pledge(self, graphql_client_query_data):
        """Test that commitment counts are independent for different pledges."""
        pledge1 = PledgeFactory.create(plan=self.plan, order=1)
        pledge2 = PledgeFactory.create(plan=self.plan, order=2)

        # Create 2 commitments for pledge1
        for _ in range(2):
            pledge_user = PledgeUser.objects.create()
            PledgeCommitment.objects.create(pledge=pledge1, pledge_user=pledge_user)

        # Create 5 commitments for pledge2
        for _ in range(5):
            pledge_user = PledgeUser.objects.create()
            PledgeCommitment.objects.create(pledge=pledge2, pledge_user=pledge_user)

        data = graphql_client_query_data(
            PLEDGES_QUERY,
            variables={'plan': self.plan.identifier},
        )

        pledges = data['plan']['pledges']
        assert len(pledges) == 2

        pledge1_data = next(p for p in pledges if p['id'] == str(pledge1.id))
        pledge2_data = next(p for p in pledges if p['id'] == str(pledge2.id))

        assert pledge1_data['commitmentCount'] == 2
        assert pledge2_data['commitmentCount'] == 5


class TestPlanFeaturesGraphQL:
    def test_enable_community_engagement_exposed_in_graphql(self, graphql_client_query_data):
        """Test that enable_community_engagement flag is exposed in GraphQL."""
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()

        data = graphql_client_query_data(
            PLAN_FEATURES_QUERY,
            variables={'plan': plan.identifier},
        )

        assert data['plan']['features']['enableCommunityEngagement'] is True

    def test_enable_community_engagement_false_exposed_in_graphql(self, graphql_client_query_data):
        """Test that enable_community_engagement=False is correctly exposed."""
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = False
        plan.features.save()

        data = graphql_client_query_data(
            PLAN_FEATURES_QUERY,
            variables={'plan': plan.identifier},
        )

        assert data['plan']['features']['enableCommunityEngagement'] is False


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
            mutation($userUuid: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userUuid: $userUuid, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userUuid': str(self.pledge_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': True,
            },
        )

        assert data['pledge']['commitToPledge']['committed'] is True
        commitment = PledgeCommitment.objects.get()
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
            mutation($userUuid: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userUuid: $userUuid, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userUuid': str(self.pledge_user.uuid),
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
            mutation($userUuid: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userUuid: $userUuid, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userUuid': str(self.pledge_user.uuid),
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
            mutation($userUuid: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userUuid: $userUuid, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userUuid': str(self.pledge_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': False,
            },
        )

        assert data['pledge']['commitToPledge']['committed'] is False
        assert PledgeCommitment.objects.count() == 0

    def test_commit_with_invalid_user_uuid_returns_error(self, graphql_client_query):
        """Test that committing with invalid user UUID returns an error."""
        fake_uuid = str(uuid.uuid4())

        response = graphql_client_query(
            """
            mutation($userUuid: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userUuid: $userUuid, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userUuid': fake_uuid,
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
            mutation($userUuid: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userUuid: $userUuid, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userUuid': str(self.pledge_user.uuid),
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
            mutation($userUuid: UUID!, $pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(userUuid: $userUuid, pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={
                'userUuid': str(self.pledge_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': True,
            },
        )

        assert 'errors' in response
        assert 'Community engagement is not enabled for this plan' in response['errors'][0]['message']
        assert PledgeCommitment.objects.count() == 0


class TestSetUserDataMutation:
    """Tests for the setUserData GraphQL mutation."""

    def test_set_user_data_sets_value(self, graphql_client_query_data):
        """Test that the mutation sets a key-value pair in user_data."""
        pledge_user = PledgeUser.objects.create()
        assert pledge_user.user_data == {}

        data = graphql_client_query_data(
            """
            mutation($userUuid: UUID!, $key: String!, $value: String!) {
              pledge {
                setUserData(userUuid: $userUuid, key: $key, value: $value) {
                  uuid
                }
              }
            }
            """,
            variables={
                'userUuid': str(pledge_user.uuid),
                'key': 'zip_code',
                'value': '01234',
            },
        )

        assert data['pledge']['setUserData']['uuid'] == str(pledge_user.uuid)

        pledge_user.refresh_from_db()
        assert pledge_user.user_data['zip_code'] == '01234'

    def test_set_user_data_updates_existing_value(self, graphql_client_query_data):
        """Test that the mutation updates an existing key."""
        pledge_user = PledgeUser.objects.create(user_data={'zip_code': '00000'})

        graphql_client_query_data(
            """
            mutation($userUuid: UUID!, $key: String!, $value: String!) {
              pledge {
                setUserData(userUuid: $userUuid, key: $key, value: $value) {
                  uuid
                }
              }
            }
            """,
            variables={
                'userUuid': str(pledge_user.uuid),
                'key': 'zip_code',
                'value': '99999',
            },
        )

        pledge_user.refresh_from_db()
        assert pledge_user.user_data['zip_code'] == '99999'

    def test_set_user_data_preserves_other_keys(self, graphql_client_query_data):
        """Test that setting a new key preserves existing keys."""
        pledge_user = PledgeUser.objects.create(user_data={'city': 'Helsinki'})

        graphql_client_query_data(
            """
            mutation($userUuid: UUID!, $key: String!, $value: String!) {
              pledge {
                setUserData(userUuid: $userUuid, key: $key, value: $value) {
                  uuid
                }
              }
            }
            """,
            variables={
                'userUuid': str(pledge_user.uuid),
                'key': 'zip_code',
                'value': '00100',
            },
        )

        pledge_user.refresh_from_db()
        assert pledge_user.user_data['city'] == 'Helsinki'
        assert pledge_user.user_data['zip_code'] == '00100'

    def test_set_user_data_with_invalid_user_uuid_returns_error(self, graphql_client_query):
        """Test that setting data with invalid user UUID returns an error."""
        fake_uuid = str(uuid.uuid4())

        response = graphql_client_query(
            """
            mutation($userUuid: UUID!, $key: String!, $value: String!) {
              pledge {
                setUserData(userUuid: $userUuid, key: $key, value: $value) {
                  uuid
                }
              }
            }
            """,
            variables={
                'userUuid': fake_uuid,
                'key': 'zip_code',
                'value': '01234',
            },
        )

        assert 'errors' in response
        assert 'PledgeUser not found' in response['errors'][0]['message']


class TestPledgeUserQuery:
    """Tests for the pledgeUser GraphQL query."""

    PLEDGE_USER_QUERY = """
        query($uuid: UUID!) {
            pledgeUser(uuid: $uuid) {
                id
                uuid
                commitments {
                    id
                    createdAt
                    pledge {
                        id
                        name
                    }
                }
            }
        }
    """

    def test_pledge_user_query_returns_user_with_commitments(self, graphql_client_query_data):
        """Test that pledgeUser query returns user and their commitments."""
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()

        pledge = PledgeFactory.create(plan=plan, name='Test Pledge')
        pledge_user = PledgeUser.objects.create()
        commitment = PledgeCommitment.objects.create(pledge=pledge, pledge_user=pledge_user)

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': str(pledge_user.uuid)},
        )

        assert data['pledgeUser'] is not None
        assert data['pledgeUser']['uuid'] == str(pledge_user.uuid)
        assert len(data['pledgeUser']['commitments']) == 1
        assert data['pledgeUser']['commitments'][0]['id'] == str(commitment.id)
        assert data['pledgeUser']['commitments'][0]['pledge']['id'] == str(pledge.id)
        assert data['pledgeUser']['commitments'][0]['pledge']['name'] == 'Test Pledge'

    def test_pledge_user_query_returns_null_for_invalid_uuid(self, graphql_client_query_data):
        """Test that pledgeUser query returns null for non-existent UUID."""
        fake_uuid = str(uuid.uuid4())

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': fake_uuid},
        )

        assert data['pledgeUser'] is None

    def test_pledge_user_query_filters_commitments_by_feature_flag(self, graphql_client_query_data):
        """Test that commitments are filtered based on enable_community_engagement flag."""
        # Create a plan with feature enabled
        plan_enabled = PlanFactory.create()
        plan_enabled.features.enable_community_engagement = True
        plan_enabled.features.save()

        # Create a plan with feature disabled
        plan_disabled = PlanFactory.create()
        plan_disabled.features.enable_community_engagement = False
        plan_disabled.features.save()

        pledge_enabled = PledgeFactory.create(plan=plan_enabled, name='Enabled Pledge')
        pledge_disabled = PledgeFactory.create(plan=plan_disabled, name='Disabled Pledge')

        pledge_user = PledgeUser.objects.create()
        PledgeCommitment.objects.create(pledge=pledge_enabled, pledge_user=pledge_user)
        PledgeCommitment.objects.create(pledge=pledge_disabled, pledge_user=pledge_user)

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': str(pledge_user.uuid)},
        )

        assert data['pledgeUser'] is not None
        # Only the commitment to the enabled pledge should be returned
        assert len(data['pledgeUser']['commitments']) == 1
        assert data['pledgeUser']['commitments'][0]['pledge']['name'] == 'Enabled Pledge'

    def test_pledge_user_query_returns_multiple_commitments(self, graphql_client_query_data):
        """Test that pledgeUser query returns all commitments for a user."""
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()

        pledge1 = PledgeFactory.create(plan=plan, name='Pledge 1')
        pledge2 = PledgeFactory.create(plan=plan, name='Pledge 2')
        pledge3 = PledgeFactory.create(plan=plan, name='Pledge 3')

        pledge_user = PledgeUser.objects.create()
        PledgeCommitment.objects.create(pledge=pledge1, pledge_user=pledge_user)
        PledgeCommitment.objects.create(pledge=pledge2, pledge_user=pledge_user)
        PledgeCommitment.objects.create(pledge=pledge3, pledge_user=pledge_user)

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': str(pledge_user.uuid)},
        )

        assert data['pledgeUser'] is not None
        assert len(data['pledgeUser']['commitments']) == 3

        pledge_names = [c['pledge']['name'] for c in data['pledgeUser']['commitments']]
        assert 'Pledge 1' in pledge_names
        assert 'Pledge 2' in pledge_names
        assert 'Pledge 3' in pledge_names
