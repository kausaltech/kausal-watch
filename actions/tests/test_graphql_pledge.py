from __future__ import annotations

import pytest

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
