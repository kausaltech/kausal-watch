from __future__ import annotations

import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.utils import timezone
from wagtail.models import Locale

import pytest

from actions.models import Pledge, PledgeCommitment, PublicUser, PublicUserSignInAttempt
from actions.models.pledge import PIN_MAX_ATTEMPTS, hash_user_token
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


ACTION_PLEDGES_QUERY = """
    query($actionId: ID!) {
        action(id: $actionId) {
            id
            pledges {
                id
                name
            }
    }
}
"""

PLEDGE_QUERY_WITH_LOCALE = f"""
    query($plan: ID!, $lang: String!, $id: ID, $slug: String) @locale(lang: $lang) {{
        plan(id: $plan) {{
            pledge(id: $id, slug: $slug) {{
                {PLEDGE_FIELDS}
            }}
        }}
    }}
"""

PLEDGES_QUERY_WITH_LOCALE = f"""
    query($plan: ID!, $lang: String!) @locale(lang: $lang) {{
        plan(id: $plan) {{
            pledges {{
                {PLEDGE_FIELDS}
            }}
        }}
    }}
"""

ACTION_PLEDGES_QUERY_WITH_LOCALE = """
    query($actionId: ID!, $lang: String!) @locale(lang: $lang) {
        action(id: $actionId) {
            id
            pledges {
                id
                name
            }
        }
    }
"""

PLEDGE_USER_QUERY_WITH_LOCALE = """
    query($uuid: UUID!, $lang: String!) @locale(lang: $lang) {
        publicUser(uuid: $uuid) {
            uuid
            commitments {
                pledge {
                    id
                    name
                }
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
            public_user = PublicUser.objects.create()
            PledgeCommitment.objects.create(pledge=pledge, public_user=public_user)

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
            public_user = PublicUser.objects.create()
            PledgeCommitment.objects.create(pledge=pledge1, public_user=public_user)

        # Create 5 commitments for pledge2
        for _ in range(5):
            public_user = PublicUser.objects.create()
            PledgeCommitment.objects.create(pledge=pledge2, public_user=public_user)

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


class TestRegisterPublicUserMutation:
    """Tests for the registerUser GraphQL mutation."""

    def test_register_user_creates_public_user(self, graphql_client_query_data):
        """Test that the mutation creates a PublicUser in the database."""
        initial_count = PublicUser.objects.count()

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

        assert PublicUser.objects.count() == initial_count + 1

        # Verify the returned UUID matches the created user
        returned_uuid = data['pledge']['registerUser']['uuid']
        public_user = PublicUser.objects.get(uuid=returned_uuid)
        assert public_user is not None
        assert public_user.user_data == {}

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
        assert PublicUser.objects.count() == 2


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
        self.public_user = PublicUser.objects.create()

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
                'userUuid': str(self.public_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': True,
            },
        )

        assert data['pledge']['commitToPledge']['committed'] is True
        commitment = PledgeCommitment.objects.get()
        assert commitment.pledge == self.pledge
        assert commitment.public_user == self.public_user

    def test_uncommit_from_pledge_removes_commitment(self, graphql_client_query_data):
        """Test that uncommitting removes the PledgeCommitment."""
        # Create a commitment first
        PledgeCommitment.objects.create(
            pledge=self.pledge,
            public_user=self.public_user,
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
                'userUuid': str(self.public_user.uuid),
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
            public_user=self.public_user,
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
                'userUuid': str(self.public_user.uuid),
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
                'userUuid': str(self.public_user.uuid),
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
        assert 'PublicUser not found' in response['errors'][0]['message']
        assert response['errors'][0]['extensions']['code'] == 'PUBLIC_USER_NOT_FOUND'

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
                'userUuid': str(self.public_user.uuid),
                'pledgeId': '99999',
                'committed': True,
            },
        )

        assert 'errors' in response
        assert 'Pledge not found' in response['errors'][0]['message']

    def test_commit_invalidates_plan_cache(self, graphql_client_query_data):
        """Test that committing to a pledge invalidates the plan's GraphQL cache."""
        old_cache_invalidated_at = self.plan.cache_invalidated_at

        graphql_client_query_data(
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
                'userUuid': str(self.public_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': True,
            },
        )

        self.plan.refresh_from_db()
        assert self.plan.cache_invalidated_at > old_cache_invalidated_at

    def test_uncommit_invalidates_plan_cache(self, graphql_client_query_data):
        """Test that uncommitting from a pledge invalidates the plan's GraphQL cache."""
        PledgeCommitment.objects.create(pledge=self.pledge, public_user=self.public_user)
        old_cache_invalidated_at = self.plan.cache_invalidated_at

        graphql_client_query_data(
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
                'userUuid': str(self.public_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': False,
            },
        )

        self.plan.refresh_from_db()
        assert self.plan.cache_invalidated_at > old_cache_invalidated_at

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
                'userUuid': str(self.public_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': True,
            },
        )

        assert 'errors' in response
        assert 'Community engagement is not enabled for this plan' in response['errors'][0]['message']
        assert PledgeCommitment.objects.count() == 0

    def test_commit_with_bearer_token_authenticates(self, graphql_client_query_data):
        """The commitToPledge mutation should authenticate via the X-Public-User-Token header alone."""
        token = self.public_user.regenerate_user_token()

        data = graphql_client_query_data(
            """
            mutation($pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={'pledgeId': str(self.pledge.id), 'committed': True},
            headers={'X-Public-User-Token': token},
        )

        assert data['pledge']['commitToPledge']['committed'] is True
        commitment = PledgeCommitment.objects.get()
        assert commitment.public_user == self.public_user

    def test_commit_bearer_token_takes_precedence_over_user_uuid(self, graphql_client_query_data):
        """If both bearer and userUuid are given, the bearer-identified user wins."""
        token = self.public_user.regenerate_user_token()
        other_user = PublicUser.objects.create()

        graphql_client_query_data(
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
                'userUuid': str(other_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': True,
            },
            headers={'X-Public-User-Token': token},
        )

        assert PledgeCommitment.objects.filter(public_user=self.public_user).exists()
        assert not PledgeCommitment.objects.filter(public_user=other_user).exists()

    def test_commit_with_uuid_rejected_when_user_has_signed_up(self, graphql_client_query):
        """Once a PublicUser has a user_token, the UUID arg must no longer authenticate."""
        self.public_user.regenerate_user_token()

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
                'userUuid': str(self.public_user.uuid),
                'pledgeId': str(self.pledge.id),
                'committed': True,
            },
        )

        assert 'errors' in response
        assert 'X-Public-User-Token' in response['errors'][0]['message']
        assert response['errors'][0]['extensions']['code'] == 'TOKEN_REQUIRED'
        assert PledgeCommitment.objects.count() == 0

    def test_commit_without_credentials_returns_error(self, graphql_client_query):
        """Omitting both bearer and userUuid must fail with an auth error."""
        response = graphql_client_query(
            """
            mutation($pledgeId: ID!, $committed: Boolean!) {
              pledge {
                commitToPledge(pledgeId: $pledgeId, committed: $committed) {
                  committed
                }
              }
            }
            """,
            variables={'pledgeId': str(self.pledge.id), 'committed': True},
        )

        assert 'errors' in response
        assert 'Authentication required' in response['errors'][0]['message']
        assert response['errors'][0]['extensions']['code'] == 'AUTHENTICATION_REQUIRED'
        assert PledgeCommitment.objects.count() == 0


class TestSetUserDataMutation:
    """Tests for the setUserData GraphQL mutation."""

    def test_set_user_data_sets_value(self, graphql_client_query_data):
        """Test that the mutation sets a key-value pair in user_data."""
        public_user = PublicUser.objects.create()
        assert public_user.user_data == {}

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
                'userUuid': str(public_user.uuid),
                'key': 'zip_code',
                'value': '01234',
            },
        )

        assert data['pledge']['setUserData']['uuid'] == str(public_user.uuid)

        public_user.refresh_from_db()
        assert public_user.user_data['zip_code'] == '01234'

    def test_set_user_data_updates_existing_value(self, graphql_client_query_data):
        """Test that the mutation updates an existing key."""
        public_user = PublicUser.objects.create(user_data={'zip_code': '00000'})

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
                'userUuid': str(public_user.uuid),
                'key': 'zip_code',
                'value': '99999',
            },
        )

        public_user.refresh_from_db()
        assert public_user.user_data['zip_code'] == '99999'

    def test_set_user_data_preserves_other_keys(self, graphql_client_query_data):
        """Test that setting a new key preserves existing keys."""
        public_user = PublicUser.objects.create(user_data={'city': 'Helsinki'})

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
                'userUuid': str(public_user.uuid),
                'key': 'zip_code',
                'value': '00100',
            },
        )

        public_user.refresh_from_db()
        assert public_user.user_data['city'] == 'Helsinki'
        assert public_user.user_data['zip_code'] == '00100'

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
        assert 'PublicUser not found' in response['errors'][0]['message']
        assert response['errors'][0]['extensions']['code'] == 'PUBLIC_USER_NOT_FOUND'

    def test_set_user_data_with_bearer_token_authenticates(self, graphql_client_query_data):
        """The setUserData mutation should authenticate via the X-Public-User-Token header alone."""
        public_user = PublicUser.objects.create()
        token = public_user.regenerate_user_token()

        graphql_client_query_data(
            """
            mutation($key: String!, $value: String!) {
              pledge {
                setUserData(key: $key, value: $value) {
                  uuid
                }
              }
            }
            """,
            variables={'key': 'zip_code', 'value': '01234'},
            headers={'X-Public-User-Token': token},
        )

        public_user.refresh_from_db()
        assert public_user.user_data['zip_code'] == '01234'


SIGN_UP_MUTATION = """
    mutation($email: String!, $terms: Boolean!, $marketing: Boolean!, $anonUuid: UUID) {
      pledge {
        signUp(email: $email, termsAccepted: $terms, marketingAccepted: $marketing, anonUuid: $anonUuid) {
          sent
        }
      }
    }
"""

SIGN_IN_MUTATION = """
    mutation($email: String!, $anonUuid: UUID) {
      pledge {
        signIn(email: $email, anonUuid: $anonUuid) {
          sent
        }
      }
    }
"""


class TestSignUpMutation:
    """Tests for the signUp GraphQL mutation."""

    def test_sign_up_creates_user_and_sends_pin(self, graphql_client_query_data):
        mail.outbox.clear()

        data = graphql_client_query_data(
            SIGN_UP_MUTATION,
            variables={'email': 'new@example.com', 'terms': True, 'marketing': True},
        )

        assert data['pledge']['signUp']['sent'] is True
        public_user = PublicUser.objects.get(email='new@example.com')
        assert public_user.terms_accepted_at is not None
        assert public_user.marketing_consented_at is not None
        assert PublicUserSignInAttempt.objects.filter(public_user=public_user).exists()
        assert len(mail.outbox) == 1
        assert 'new@example.com' in mail.outbox[0].to

    def test_sign_up_marketing_opt_out_does_not_set_consent(self, graphql_client_query_data):
        graphql_client_query_data(
            SIGN_UP_MUTATION,
            variables={'email': 'optout@example.com', 'terms': True, 'marketing': False},
        )

        public_user = PublicUser.objects.get(email='optout@example.com')
        assert public_user.marketing_consented_at is None

    def test_sign_up_errors_when_email_exists(self, graphql_client_query):
        PublicUser.objects.create(email='exists@example.com')

        response = graphql_client_query(
            SIGN_UP_MUTATION,
            variables={'email': 'exists@example.com', 'terms': True, 'marketing': False},
        )

        assert 'errors' in response
        assert 'already exists' in response['errors'][0]['message']
        assert response['errors'][0]['extensions']['code'] == 'ACCOUNT_EXISTS'

    def test_sign_up_errors_when_terms_not_accepted(self, graphql_client_query):
        response = graphql_client_query(
            SIGN_UP_MUTATION,
            variables={'email': 'a@example.com', 'terms': False, 'marketing': False},
        )

        assert 'errors' in response
        assert 'Terms' in response['errors'][0]['message']
        assert response['errors'][0]['extensions']['code'] == 'TERMS_NOT_ACCEPTED'

    def test_sign_up_errors_when_email_is_blank(self, graphql_client_query):
        response = graphql_client_query(
            SIGN_UP_MUTATION,
            variables={'email': '   ', 'terms': True, 'marketing': False},
        )

        assert 'errors' in response
        assert response['errors'][0]['extensions']['code'] == 'EMAIL_REQUIRED'

    def test_sign_up_normalizes_email(self, graphql_client_query_data):
        graphql_client_query_data(
            SIGN_UP_MUTATION,
            variables={'email': '  Foo@Example.COM  ', 'terms': True, 'marketing': False},
        )

        assert PublicUser.objects.filter(email='foo@example.com').exists()

    def test_sign_up_rolls_back_on_email_failure(self, graphql_client_query):
        with patch(
            'actions.public_user_auth.send_pin_email',
            side_effect=RuntimeError('SMTP down'),
        ):
            response = graphql_client_query(
                SIGN_UP_MUTATION,
                variables={'email': 'rollback@example.com', 'terms': True, 'marketing': False},
            )

        assert 'errors' in response
        assert response['errors'][0]['extensions']['code'] == 'EMAIL_SEND_FAILED'
        assert not PublicUser.objects.filter(email='rollback@example.com').exists()
        assert not PublicUserSignInAttempt.objects.filter(public_user__email='rollback@example.com').exists()

    def test_sign_up_stores_anon_uuid_on_attempt(self, graphql_client_query_data):
        anon_uuid = uuid.uuid4()
        graphql_client_query_data(
            SIGN_UP_MUTATION,
            variables={
                'email': 'merge@example.com',
                'terms': True,
                'marketing': False,
                'anonUuid': str(anon_uuid),
            },
        )

        public_user = PublicUser.objects.get(email='merge@example.com')
        attempt = PublicUserSignInAttempt.objects.get(public_user=public_user)
        assert attempt.anon_uuid == anon_uuid


class TestSignInMutation:
    """Tests for the signIn GraphQL mutation."""

    def test_sign_in_sends_pin_for_existing_user(self, graphql_client_query_data):
        public_user = PublicUser.objects.create(email='hello@example.com')
        mail.outbox.clear()

        data = graphql_client_query_data(
            SIGN_IN_MUTATION,
            variables={'email': 'hello@example.com'},
        )

        assert data['pledge']['signIn']['sent'] is True
        assert PublicUserSignInAttempt.objects.filter(public_user=public_user).exists()
        assert len(mail.outbox) == 1

    def test_sign_in_errors_when_email_not_found(self, graphql_client_query):
        response = graphql_client_query(
            SIGN_IN_MUTATION,
            variables={'email': 'unknown@example.com'},
        )

        assert 'errors' in response
        assert 'No account' in response['errors'][0]['message']
        assert response['errors'][0]['extensions']['code'] == 'ACCOUNT_NOT_FOUND'

    def test_sign_in_cooldown_enforced(self, graphql_client_query, graphql_client_query_data):
        PublicUser.objects.create(email='hello@example.com')

        graphql_client_query_data(SIGN_IN_MUTATION, variables={'email': 'hello@example.com'})
        response = graphql_client_query(SIGN_IN_MUTATION, variables={'email': 'hello@example.com'})

        assert 'errors' in response
        assert 'wait' in response['errors'][0]['message'].lower()
        assert response['errors'][0]['extensions']['code'] == 'COOLDOWN_ACTIVE'

    def test_sign_in_allows_after_cooldown_window(self, graphql_client_query_data):
        public_user = PublicUser.objects.create(email='hello@example.com')
        graphql_client_query_data(SIGN_IN_MUTATION, variables={'email': 'hello@example.com'})
        attempt = PublicUserSignInAttempt.objects.get(public_user=public_user)
        attempt.issued_at = timezone.now() - timedelta(minutes=5)
        attempt.save(update_fields=['issued_at'])

        data = graphql_client_query_data(SIGN_IN_MUTATION, variables={'email': 'hello@example.com'})

        assert data['pledge']['signIn']['sent'] is True

    def test_sign_in_normalizes_email(self, graphql_client_query_data):
        PublicUser.objects.create(email='hello@example.com')

        data = graphql_client_query_data(
            SIGN_IN_MUTATION,
            variables={'email': '  HELLO@Example.com '},
        )

        assert data['pledge']['signIn']['sent'] is True

    def test_sign_in_rate_limited_returns_error(self, graphql_client_query):
        from actions.public_user_auth import SIGN_IN_RATE_LIMIT

        max_per_minute = int(SIGN_IN_RATE_LIMIT.split('/')[0])
        for _ in range(max_per_minute):
            PublicUser.objects.get_or_create(email='ratelimit@example.com')
            graphql_client_query(SIGN_IN_MUTATION, variables={'email': f'ratelimit{_}@example.com'})

        PublicUser.objects.get_or_create(email='ratelimit-over@example.com')
        response = graphql_client_query(SIGN_IN_MUTATION, variables={'email': 'ratelimit-over@example.com'})

        assert 'errors' in response
        assert response['errors'][0]['extensions']['code'] == 'RATE_LIMITED'

    def test_sign_in_rolls_back_attempt_on_email_failure(self, graphql_client_query):
        public_user = PublicUser.objects.create(email='alice@example.com')
        prior_attempt, _ = PublicUserSignInAttempt.create_for(public_user)
        # Backdate the prior attempt so the cooldown doesn't itself block the retry.
        # The point of this test is to assert all fields are preserved unchanged.
        prior_attempt.issued_at = timezone.now() - timedelta(minutes=5)
        prior_attempt.attempts = 3
        prior_attempt.save(update_fields=['issued_at', 'attempts'])
        snapshot = {
            'pin_hash': prior_attempt.pin_hash,
            'pin_salt': prior_attempt.pin_salt,
            'issued_at': prior_attempt.issued_at,
            'expires_at': prior_attempt.expires_at,
            'attempts': prior_attempt.attempts,
        }

        with patch(
            'actions.public_user_auth.send_pin_email',
            side_effect=RuntimeError('SMTP down'),
        ):
            response = graphql_client_query(
                SIGN_IN_MUTATION,
                variables={'email': 'alice@example.com'},
            )

        assert 'errors' in response
        assert response['errors'][0]['extensions']['code'] == 'EMAIL_SEND_FAILED'
        prior_attempt.refresh_from_db()
        for field, expected in snapshot.items():
            assert getattr(prior_attempt, field) == expected, f'{field} was modified despite rollback'

    def test_sign_in_stores_anon_uuid_on_attempt(self, graphql_client_query_data):
        public_user = PublicUser.objects.create(email='hello@example.com')
        anon_uuid = uuid.uuid4()

        graphql_client_query_data(
            SIGN_IN_MUTATION,
            variables={'email': 'hello@example.com', 'anonUuid': str(anon_uuid)},
        )

        attempt = PublicUserSignInAttempt.objects.get(public_user=public_user)
        assert attempt.anon_uuid == anon_uuid


VERIFY_PIN_MUTATION = """
    mutation($email: String!, $pin: String!) {
      pledge {
        verifyPin(email: $email, pin: $pin) {
          userToken
          pledgeIds
        }
      }
    }
"""


class TestVerifyPinMutation:
    """Tests for the verifyPin GraphQL mutation."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()
        self.public_user = PublicUser.objects.create(email='alice@example.com')

    def _issue_pin(self, anon_uuid: uuid.UUID | None = None) -> str:
        _, raw_pin = PublicUserSignInAttempt.create_for(self.public_user, anon_uuid=anon_uuid)
        return raw_pin

    def test_verify_pin_success_returns_token(self, graphql_client_query_data):
        raw_pin = self._issue_pin()

        data = graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        returned_token = data['pledge']['verifyPin']['userToken']
        assert returned_token
        self.public_user.refresh_from_db()
        assert self.public_user.user_token == hash_user_token(returned_token)
        assert not PublicUserSignInAttempt.objects.filter(public_user=self.public_user).exists()

    def test_verify_pin_sets_email_verified_at_on_first_verify(self, graphql_client_query_data):
        raw_pin = self._issue_pin()

        graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        self.public_user.refresh_from_db()
        assert self.public_user.email_verified_at is not None

    def test_verify_pin_does_not_overwrite_email_verified_at(self, graphql_client_query_data):
        earlier = timezone.now() - timedelta(days=1)
        self.public_user.email_verified_at = earlier
        self.public_user.save(update_fields=['email_verified_at'])
        raw_pin = self._issue_pin()

        graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        self.public_user.refresh_from_db()
        assert self.public_user.email_verified_at == earlier

    def test_verify_pin_rotates_existing_token(self, graphql_client_query_data):
        old_raw = self.public_user.regenerate_user_token()
        old_hash = self.public_user.user_token
        raw_pin = self._issue_pin()

        data = graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        new_token = data['pledge']['verifyPin']['userToken']
        assert new_token != old_raw
        self.public_user.refresh_from_db()
        assert self.public_user.user_token != old_hash

    def test_verify_pin_returns_existing_pledge_ids(self, graphql_client_query_data):
        pledge = PledgeFactory.create(plan=self.plan)
        PledgeCommitment.objects.create(pledge=pledge, public_user=self.public_user)
        raw_pin = self._issue_pin()

        data = graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        assert data['pledge']['verifyPin']['pledgeIds'] == [str(pledge.id)]

    def test_verify_pin_merges_anonymous_commitments(self, graphql_client_query_data):
        pledge = PledgeFactory.create(plan=self.plan)
        anon = PublicUser.objects.create()
        PledgeCommitment.objects.create(pledge=pledge, public_user=anon)
        raw_pin = self._issue_pin(anon_uuid=anon.uuid)

        data = graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        assert data['pledge']['verifyPin']['pledgeIds'] == [str(pledge.id)]
        assert PledgeCommitment.objects.filter(pledge=pledge, public_user=self.public_user).exists()
        assert not PublicUser.objects.filter(uuid=anon.uuid).exists()

    def test_verify_pin_merges_subsequent_anon_into_existing_account(self, graphql_client_query_data):
        existing_pledge = PledgeFactory.create(plan=self.plan, slug='already-committed')
        PledgeCommitment.objects.create(pledge=existing_pledge, public_user=self.public_user)
        new_pledge = PledgeFactory.create(plan=self.plan, slug='from-second-device')
        second_anon = PublicUser.objects.create()
        PledgeCommitment.objects.create(pledge=new_pledge, public_user=second_anon)
        raw_pin = self._issue_pin(anon_uuid=second_anon.uuid)

        data = graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        assert set(data['pledge']['verifyPin']['pledgeIds']) == {str(existing_pledge.id), str(new_pledge.id)}
        assert PledgeCommitment.objects.filter(pledge=new_pledge, public_user=self.public_user).exists()
        assert not PublicUser.objects.filter(uuid=second_anon.uuid).exists()

    def test_verify_pin_dedupes_overlapping_commitments_on_merge(self, graphql_client_query_data):
        pledge = PledgeFactory.create(plan=self.plan)
        PledgeCommitment.objects.create(pledge=pledge, public_user=self.public_user)
        anon = PublicUser.objects.create()
        PledgeCommitment.objects.create(pledge=pledge, public_user=anon)
        raw_pin = self._issue_pin(anon_uuid=anon.uuid)

        graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        assert PledgeCommitment.objects.filter(pledge=pledge, public_user=self.public_user).count() == 1
        assert not PublicUser.objects.filter(uuid=anon.uuid).exists()
        assert PledgeCommitment.objects.count() == 1

    def test_verify_pin_merges_anon_user_data_into_verified_user(self, graphql_client_query_data):
        anon = PublicUser.objects.create(user_data={'zip_code': '95695'})
        raw_pin = self._issue_pin(anon_uuid=anon.uuid)

        graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        self.public_user.refresh_from_db()
        assert self.public_user.user_data == {'zip_code': '95695'}

    def test_verify_pin_anon_user_data_overrides_existing_on_conflict(self, graphql_client_query_data):
        self.public_user.user_data = {'zip_code': '12345', 'city': 'Oldtown'}
        self.public_user.save(update_fields=['user_data'])
        anon = PublicUser.objects.create(user_data={'zip_code': '95695'})
        raw_pin = self._issue_pin(anon_uuid=anon.uuid)

        graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        self.public_user.refresh_from_db()
        assert self.public_user.user_data == {'zip_code': '95695', 'city': 'Oldtown'}

    def test_verify_pin_user_data_merge_preserves_verified_only_keys(self, graphql_client_query_data):
        self.public_user.user_data = {'city': 'Newtown'}
        self.public_user.save(update_fields=['user_data'])
        anon = PublicUser.objects.create(user_data={'zip_code': '95695'})
        raw_pin = self._issue_pin(anon_uuid=anon.uuid)

        graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        self.public_user.refresh_from_db()
        assert self.public_user.user_data == {'city': 'Newtown', 'zip_code': '95695'}

    def test_verify_pin_invalidates_plan_cache_when_merge_deletes_duplicates(self, graphql_client_query_data):
        pledge = PledgeFactory.create(plan=self.plan)
        PledgeCommitment.objects.create(pledge=pledge, public_user=self.public_user)
        anon = PublicUser.objects.create()
        PledgeCommitment.objects.create(pledge=pledge, public_user=anon)
        raw_pin = self._issue_pin(anon_uuid=anon.uuid)
        self.plan.refresh_from_db()
        cache_invalidated_before = self.plan.cache_invalidated_at

        graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        self.plan.refresh_from_db()
        assert self.plan.cache_invalidated_at > cache_invalidated_before

    def test_verify_pin_skips_merge_when_anon_uuid_has_email(self, graphql_client_query_data):
        pledge = PledgeFactory.create(plan=self.plan)
        bob = PublicUser.objects.create(email='bob@example.com')
        PledgeCommitment.objects.create(pledge=pledge, public_user=bob)
        raw_pin = self._issue_pin(anon_uuid=bob.uuid)

        data = graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        assert data['pledge']['verifyPin']['pledgeIds'] == []
        assert PledgeCommitment.objects.filter(pledge=pledge, public_user=bob).exists()
        assert PublicUser.objects.filter(uuid=bob.uuid).exists()

    def test_verify_pin_with_unknown_anon_uuid_no_op(self, graphql_client_query_data):
        raw_pin = self._issue_pin(anon_uuid=uuid.uuid4())

        data = graphql_client_query_data(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        assert data['pledge']['verifyPin']['userToken']

    def test_verify_pin_wrong_pin_returns_error(self, graphql_client_query):
        raw_pin = self._issue_pin()
        wrong = '000000' if raw_pin != '000000' else '111111'

        response = graphql_client_query(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': wrong},
        )

        assert 'errors' in response
        assert 'Invalid PIN' in response['errors'][0]['message']
        assert response['errors'][0]['extensions']['code'] == 'INVALID_PIN'
        assert PublicUserSignInAttempt.objects.filter(public_user=self.public_user).exists()

    def test_verify_pin_expired_returns_error(self, graphql_client_query):
        raw_pin = self._issue_pin()
        attempt = PublicUserSignInAttempt.objects.get(public_user=self.public_user)
        attempt.expires_at = timezone.now() - timedelta(minutes=1)
        attempt.save(update_fields=['expires_at'])

        response = graphql_client_query(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        assert 'errors' in response
        assert 'expired' in response['errors'][0]['message'].lower()
        assert response['errors'][0]['extensions']['code'] == 'PIN_EXPIRED'

    def test_verify_pin_attempts_exhausted_returns_error(self, graphql_client_query):
        raw_pin = self._issue_pin()
        attempt = PublicUserSignInAttempt.objects.get(public_user=self.public_user)
        attempt.attempts = PIN_MAX_ATTEMPTS
        attempt.save(update_fields=['attempts'])

        response = graphql_client_query(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': raw_pin},
        )

        assert 'errors' in response
        assert 'Too many attempts' in response['errors'][0]['message']
        assert response['errors'][0]['extensions']['code'] == 'PIN_LOCKED'

    def test_verify_pin_no_account_returns_invalid_pin(self, graphql_client_query):
        response = graphql_client_query(
            VERIFY_PIN_MUTATION,
            variables={'email': 'nobody@example.com', 'pin': '000000'},
        )

        assert 'errors' in response
        assert 'Invalid PIN' in response['errors'][0]['message']
        assert response['errors'][0]['extensions']['code'] == 'INVALID_PIN'

    def test_verify_pin_no_active_attempt_returns_error(self, graphql_client_query):
        response = graphql_client_query(
            VERIFY_PIN_MUTATION,
            variables={'email': 'alice@example.com', 'pin': '000000'},
        )

        assert 'errors' in response
        assert 'No active sign-in attempt' in response['errors'][0]['message']
        assert response['errors'][0]['extensions']['code'] == 'NO_ACTIVE_ATTEMPT'


class TestPledgeBodyField:
    """Tests for the Pledge body StreamField GraphQL handling."""

    @pytest.fixture(autouse=True)
    def setup(self):
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()
        self.plan = plan

    def test_pledge_body_field_returns_typed_blocks(self, graphql_client_query_data):
        """Test that the body field returns properly typed block data."""
        from wagtail.rich_text import RichText

        # Create a pledge with body content
        pledge = PledgeFactory.create(plan=self.plan)
        pledge.body = [
            ('paragraph', RichText('<p>This is a test paragraph.</p>')),
        ]
        pledge.save()

        query = """
            query($plan: ID!, $id: ID) {
                plan(id: $plan) {
                    pledge(id: $id) {
                        id
                        body {
                            __typename
                            ... on RichTextBlock {
                                value
                            }
                        }
                    }
                }
            }
        """

        data = graphql_client_query_data(
            query,
            variables={'plan': self.plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is not None
        assert data['plan']['pledge']['body'] is not None
        assert len(data['plan']['pledge']['body']) == 1
        assert data['plan']['pledge']['body'][0]['__typename'] == 'RichTextBlock'

    def test_pledge_body_field_handles_null_value(self, graphql_client_query_data):
        """Test that the body field handles null/empty values correctly."""
        pledge = PledgeFactory.create(plan=self.plan)
        pledge.body = None
        pledge.save()

        query = """
            query($plan: ID!, $id: ID) {
                plan(id: $plan) {
                    pledge(id: $id) {
                        id
                        body {
                            __typename
                        }
                    }
                }
            }
        """

        data = graphql_client_query_data(
            query,
            variables={'plan': self.plan.identifier, 'id': str(pledge.id)},
        )

        assert data['plan']['pledge'] is not None
        # Empty/null StreamField returns empty list, not None
        assert data['plan']['pledge']['body'] == []


class TestPublicUserQuery:
    """Tests for the publicUser GraphQL query."""

    PLEDGE_USER_QUERY = """
        query($uuid: UUID!) {
            publicUser(uuid: $uuid) {
                id
                uuid
                userData
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

    def test_public_user_query_returns_user_with_commitments(self, graphql_client_query_data):
        """Test that publicUser query returns user and their commitments."""
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()

        pledge = PledgeFactory.create(plan=plan, name='Test Pledge')
        public_user = PublicUser.objects.create()
        commitment = PledgeCommitment.objects.create(pledge=pledge, public_user=public_user)

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': str(public_user.uuid)},
        )

        assert data['publicUser'] is not None
        assert data['publicUser']['uuid'] == str(public_user.uuid)
        assert len(data['publicUser']['commitments']) == 1
        assert data['publicUser']['commitments'][0]['id'] == str(commitment.id)
        assert data['publicUser']['commitments'][0]['pledge']['id'] == str(pledge.id)
        assert data['publicUser']['commitments'][0]['pledge']['name'] == 'Test Pledge'

    def test_public_user_query_returns_null_for_invalid_uuid(self, graphql_client_query_data):
        """Test that publicUser query returns null for non-existent UUID."""
        fake_uuid = str(uuid.uuid4())

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': fake_uuid},
        )

        assert data['publicUser'] is None

    def test_public_user_query_filters_commitments_by_feature_flag(self, graphql_client_query_data):
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

        public_user = PublicUser.objects.create()
        PledgeCommitment.objects.create(pledge=pledge_enabled, public_user=public_user)
        PledgeCommitment.objects.create(pledge=pledge_disabled, public_user=public_user)

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': str(public_user.uuid)},
        )

        assert data['publicUser'] is not None
        # Only the commitment to the enabled pledge should be returned
        assert len(data['publicUser']['commitments']) == 1
        assert data['publicUser']['commitments'][0]['pledge']['name'] == 'Enabled Pledge'

    def test_public_user_query_returns_multiple_commitments(self, graphql_client_query_data):
        """Test that publicUser query returns all commitments for a user."""
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()

        pledge1 = PledgeFactory.create(plan=plan, name='Pledge 1')
        pledge2 = PledgeFactory.create(plan=plan, name='Pledge 2')
        pledge3 = PledgeFactory.create(plan=plan, name='Pledge 3')

        public_user = PublicUser.objects.create()
        PledgeCommitment.objects.create(pledge=pledge1, public_user=public_user)
        PledgeCommitment.objects.create(pledge=pledge2, public_user=public_user)
        PledgeCommitment.objects.create(pledge=pledge3, public_user=public_user)

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': str(public_user.uuid)},
        )

        assert data['publicUser'] is not None
        assert len(data['publicUser']['commitments']) == 3

        pledge_names = [c['pledge']['name'] for c in data['publicUser']['commitments']]
        assert 'Pledge 1' in pledge_names
        assert 'Pledge 2' in pledge_names
        assert 'Pledge 3' in pledge_names

    def test_public_user_query_filters_commitments_by_plan(self, graphql_client_query_data):
        """Test that commitments can be filtered by plan identifier."""
        plan1 = PlanFactory.create()
        plan1.features.enable_community_engagement = True
        plan1.features.save()

        plan2 = PlanFactory.create()
        plan2.features.enable_community_engagement = True
        plan2.features.save()

        pledge1 = PledgeFactory.create(plan=plan1, name='Plan 1 Pledge')
        pledge2 = PledgeFactory.create(plan=plan2, name='Plan 2 Pledge')

        public_user = PublicUser.objects.create()
        PledgeCommitment.objects.create(pledge=pledge1, public_user=public_user)
        PledgeCommitment.objects.create(pledge=pledge2, public_user=public_user)

        # Query with plan filter
        query_with_plan = """
            query($uuid: UUID!, $plan: ID) {
                publicUser(uuid: $uuid) {
                    commitments(plan: $plan) {
                        pledge {
                            name
                        }
                    }
                }
            }
        """

        data = graphql_client_query_data(
            query_with_plan,
            variables={'uuid': str(public_user.uuid), 'plan': plan1.identifier},
        )

        assert data['publicUser'] is not None
        assert len(data['publicUser']['commitments']) == 1
        assert data['publicUser']['commitments'][0]['pledge']['name'] == 'Plan 1 Pledge'

    def test_public_user_query_returns_user_data(self, graphql_client_query_data):
        public_user = PublicUser.objects.create(user_data={'zip_code': '90210', 'city': 'Beverly Hills'})

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': str(public_user.uuid)},
        )

        assert data['publicUser'] is not None
        user_data = json.loads(data['publicUser']['userData'])
        assert user_data == {'zip_code': '90210', 'city': 'Beverly Hills'}

    def test_public_user_query_returns_empty_user_data(self, graphql_client_query_data):
        public_user = PublicUser.objects.create()

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': str(public_user.uuid)},
        )

        assert data['publicUser'] is not None
        assert json.loads(data['publicUser']['userData']) == {}

    def test_public_user_query_does_not_expose_user_token(self, graphql_client_query):
        """The user_token must never be queryable via the publicUser node."""
        public_user = PublicUser.objects.create()
        public_user.regenerate_user_token()
        query = """
            query($uuid: UUID!) {
                publicUser(uuid: $uuid) {
                    uuid
                    userToken
                }
            }
        """

        response = graphql_client_query(query, variables={'uuid': str(public_user.uuid)})

        assert 'errors' in response
        assert any('userToken' in error['message'] for error in response['errors'])
        data = response.get('data') or {}
        returned = data.get('publicUser') or {}
        returned_token = returned.get('userToken')
        assert returned_token is None

    def test_public_user_query_returns_null_for_signed_up_user_without_bearer(self, graphql_client_query_data):
        """Once a user has signed up, the UUID query must require a matching bearer header."""
        public_user = PublicUser.objects.create()
        public_user.regenerate_user_token()

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': str(public_user.uuid)},
        )

        assert data['publicUser'] is None

    def test_public_user_query_returns_null_when_bearer_belongs_to_other_user(self, graphql_client_query_data):
        """A signed-up user's data is hidden when the bearer header is for someone else."""
        public_user = PublicUser.objects.create()
        public_user.regenerate_user_token()

        other_user = PublicUser.objects.create()
        other_token = other_user.regenerate_user_token()

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': str(public_user.uuid)},
            headers={'X-Public-User-Token': other_token},
        )

        assert data['publicUser'] is None

    def test_public_user_query_returns_signed_up_user_when_bearer_resolves_to_them(self, graphql_client_query_data):
        """A signed-up user can read their own data by presenting their own bearer token."""
        public_user = PublicUser.objects.create()
        token = public_user.regenerate_user_token()

        data = graphql_client_query_data(
            self.PLEDGE_USER_QUERY,
            variables={'uuid': str(public_user.uuid)},
            headers={'X-Public-User-Token': token},
        )

        assert data['publicUser'] is not None
        assert data['publicUser']['uuid'] == str(public_user.uuid)

    def test_public_user_query_returns_bearer_user_when_no_uuid(self, graphql_client_query_data):
        """Without a uuid argument, the query resolves to the bearer-identified user."""
        public_user = PublicUser.objects.create(email='alice@example.com')
        token = public_user.regenerate_user_token()
        query = """
            query {
                publicUser {
                    uuid
                    email
                }
            }
        """

        data = graphql_client_query_data(query, headers={'X-Public-User-Token': token})

        assert data['publicUser'] is not None
        assert data['publicUser']['uuid'] == str(public_user.uuid)
        assert data['publicUser']['email'] == 'alice@example.com'

    def test_public_user_query_returns_null_when_no_uuid_and_no_bearer(self, graphql_client_query_data):
        """Without either a uuid argument or a bearer header, the query returns null."""
        query = 'query { publicUser { uuid } }'

        data = graphql_client_query_data(query)

        assert data['publicUser'] is None

    def test_email_field_is_null_without_matching_bearer(self, graphql_client_query_data):
        """Defensive: an email accidentally set on an anon row still requires a matching bearer to read."""
        public_user = PublicUser.objects.create()
        public_user.email = 'leaked@example.com'
        public_user.save(update_fields=['email'])
        query = """
            query($uuid: UUID!) {
                publicUser(uuid: $uuid) {
                    uuid
                    email
                }
            }
        """

        data = graphql_client_query_data(query, variables={'uuid': str(public_user.uuid)})

        assert data['publicUser'] is not None
        assert data['publicUser']['email'] is None


class TestPledgeCommitmentCountAnnotation:
    """Test that commitment count works correctly via the annotated queryset."""

    @pytest.fixture(autouse=True)
    def setup(self):
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()
        self.plan = plan

    def test_commitment_count_after_commit_mutation(self, graphql_client_query_data):
        """Test that commitmentCount is correct after a commit mutation."""
        pledge = PledgeFactory.create(plan=self.plan)
        public_user = PublicUser.objects.create()

        # Commit to the pledge
        graphql_client_query_data(
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
                'userUuid': str(public_user.uuid),
                'pledgeId': str(pledge.id),
                'committed': True,
            },
        )

        # Query the pledges list (uses the annotated queryset) and verify the count
        graphql_client_query_data(
            """
            query($plan: ID!) {
                plan(id: $plan) {
                    pledges {
                        id
                        commitmentCount
                    }
                }
            }
            """,
            variables={'plan': self.plan.identifier},
        )


class TestPledgeLocaleGraphQL:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create(
            primary_language='en',
            other_languages=['fi'],
        )
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()
        self.action = ActionFactory.create(plan=self.plan)
        self.primary_pledge = PledgeFactory.create(
            plan=self.plan,
            name='English pledge',
            slug='pledge-locale',
            actions=[self.action],
        )
        fi_locale, _ = Locale.objects.get_or_create(language_code='fi')
        self.fi_pledge = self.primary_pledge.copy_for_translation(fi_locale)
        self.fi_pledge.name = 'Suomenkielinen lupaus'
        self.fi_pledge.actions.set([self.action])
        self.fi_pledge.uuid = uuid.uuid4()
        self.fi_pledge.save()

    def test_pledges_query_returns_only_requested_locale_rows(self, graphql_client_query_data):
        data_fi = graphql_client_query_data(
            PLEDGES_QUERY_WITH_LOCALE,
            variables={'plan': self.plan.identifier, 'lang': 'fi'},
        )
        assert len(data_fi['plan']['pledges']) == 1
        assert data_fi['plan']['pledges'][0]['id'] == str(self.fi_pledge.id)
        assert data_fi['plan']['pledges'][0]['name'] == 'Suomenkielinen lupaus'

        data_en = graphql_client_query_data(
            PLEDGES_QUERY_WITH_LOCALE,
            variables={'plan': self.plan.identifier, 'lang': 'en'},
        )
        assert len(data_en['plan']['pledges']) == 1
        assert data_en['plan']['pledges'][0]['id'] == str(self.primary_pledge.id)
        assert data_en['plan']['pledges'][0]['name'] == 'English pledge'

    def test_pledge_query_by_id_returns_requested_locale_translation(self, graphql_client_query_data):
        data = graphql_client_query_data(
            PLEDGE_QUERY_WITH_LOCALE,
            variables={
                'plan': self.plan.identifier,
                'lang': 'fi',
                'id': str(self.primary_pledge.id),
            },
        )
        assert data['plan']['pledge'] is not None
        assert data['plan']['pledge']['id'] == str(self.fi_pledge.id)
        assert data['plan']['pledge']['name'] == 'Suomenkielinen lupaus'

    def test_pledge_query_by_slug_uses_requested_locale(self, graphql_client_query_data):
        data = graphql_client_query_data(
            PLEDGE_QUERY_WITH_LOCALE,
            variables={
                'plan': self.plan.identifier,
                'lang': 'fi',
                'slug': 'pledge-locale',
            },
        )
        assert data['plan']['pledge'] is not None
        assert data['plan']['pledge']['id'] == str(self.fi_pledge.id)
        assert data['plan']['pledge']['name'] == 'Suomenkielinen lupaus'

    def test_action_pledges_resolve_requested_locale(self, graphql_client_query_data):
        data = graphql_client_query_data(
            ACTION_PLEDGES_QUERY_WITH_LOCALE,
            variables={'actionId': str(self.action.id), 'lang': 'fi'},
        )
        assert len(data['action']['pledges']) == 1
        assert data['action']['pledges'][0]['id'] == str(self.fi_pledge.id)
        assert data['action']['pledges'][0]['name'] == 'Suomenkielinen lupaus'

    def test_commit_mutation_with_translated_pledge_id_uses_primary_locale(self, graphql_client_query_data):
        public_user = PublicUser.objects.create()
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
                'userUuid': str(public_user.uuid),
                'pledgeId': str(self.fi_pledge.id),
                'committed': True,
            },
        )

        assert data['pledge']['commitToPledge']['committed'] is True
        commitment = PledgeCommitment.objects.get(public_user=public_user)
        assert commitment.pledge_id == self.primary_pledge.id

    def test_commitment_count_is_shared_between_locale_copies(self, graphql_client_query_data):
        public_user = PublicUser.objects.create()
        PledgeCommitment.objects.create(pledge=self.primary_pledge, public_user=public_user)

        data_fi = graphql_client_query_data(
            PLEDGE_QUERY_WITH_LOCALE,
            variables={
                'plan': self.plan.identifier,
                'lang': 'fi',
                'id': str(self.primary_pledge.id),
            },
        )
        assert data_fi['plan']['pledge']['id'] == str(self.fi_pledge.id)
        assert data_fi['plan']['pledge']['commitmentCount'] == 1

        data_en = graphql_client_query_data(
            PLEDGE_QUERY_WITH_LOCALE,
            variables={
                'plan': self.plan.identifier,
                'lang': 'en',
                'id': str(self.primary_pledge.id),
            },
        )
        assert data_en['plan']['pledge']['id'] == str(self.primary_pledge.id)
        assert data_en['plan']['pledge']['commitmentCount'] == 1

    def test_public_user_commitments_resolve_to_requested_locale(self, graphql_client_query_data):
        public_user = PublicUser.objects.create()
        PledgeCommitment.objects.create(pledge=self.primary_pledge, public_user=public_user)

        data = graphql_client_query_data(
            PLEDGE_USER_QUERY_WITH_LOCALE,
            variables={'uuid': str(public_user.uuid), 'lang': 'fi'},
        )

        assert data['publicUser'] is not None
        assert len(data['publicUser']['commitments']) == 1
        assert data['publicUser']['commitments'][0]['pledge']['id'] == str(self.fi_pledge.id)
        assert data['publicUser']['commitments'][0]['pledge']['name'] == 'Suomenkielinen lupaus'


class TestActionPledgesFeatureFlag:
    """Test that pledges on ActionNode are gated behind enable_community_engagement."""

    def test_action_pledges_returned_when_feature_enabled(self, graphql_client_query_data):
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = True
        plan.features.save()

        action = ActionFactory.create(plan=plan)
        pledge = PledgeFactory.create(plan=plan, actions=[action])

        data = graphql_client_query_data(
            ACTION_PLEDGES_QUERY,
            variables={'actionId': str(action.id)},
        )

        pledges = data['action']['pledges']
        assert len(pledges) == 1
        assert pledges[0]['id'] == str(pledge.id)

    def test_action_pledges_empty_when_feature_disabled(self, graphql_client_query_data):
        plan = PlanFactory.create()
        plan.features.enable_community_engagement = False
        plan.features.save()

        action = ActionFactory.create(plan=plan)
        PledgeFactory.create(plan=plan, actions=[action])

        data = graphql_client_query_data(
            ACTION_PLEDGES_QUERY,
            variables={'actionId': str(action.id)},
        )

        assert data['action']['pledges'] == []
