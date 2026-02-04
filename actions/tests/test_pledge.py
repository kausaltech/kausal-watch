from __future__ import annotations

import uuid

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError

import pytest

from actions.models import Pledge, PledgeCommitment, PledgeUser
from actions.tests.factories import ActionFactory, PlanFactory, PledgeFactory

pytestmark = pytest.mark.django_db


class TestPledge:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_pledge_creation(self):
        """Test that a Pledge can be created with all fields."""
        pledge = Pledge.objects.create(
            plan=self.plan,
            name='Test Pledge',
            slug='test-pledge',
            description='A test pledge description',
            resident_count=100,
            impact_statement='We save 100kg CO₂e each year',
            local_equivalency="That's equivalent to 10 round trips",
        )

        assert pledge.name == 'Test Pledge'
        assert pledge.slug == 'test-pledge'
        assert pledge.plan == self.plan
        assert pledge.resident_count == 100

    def test_pledge_slug_unique_per_plan(self):
        """Test that pledge slugs must be unique within a plan."""
        Pledge.objects.create(
            plan=self.plan,
            name='First Pledge',
            slug='test-pledge',
        )

        # Creating another pledge with same slug in same plan should raise IntegrityError
        with pytest.raises(IntegrityError):
            Pledge.objects.create(
                plan=self.plan,
                name='Second Pledge',
                slug='test-pledge',
            )

    def test_pledge_slug_unique_across_different_plans(self):
        """Test that the same slug can be used in different plans."""
        other_plan = PlanFactory.create()

        pledge1 = Pledge.objects.create(
            plan=self.plan,
            name='First Pledge',
            slug='same-slug',
        )
        pledge2 = Pledge.objects.create(
            plan=other_plan,
            name='Second Pledge',
            slug='same-slug',
        )

        assert pledge1.slug == pledge2.slug
        assert pledge1.plan != pledge2.plan

    def test_feature_flag_in_public_fields(self):
        """Test that enable_community_engagement is in public_fields."""
        assert 'enable_community_engagement' in self.plan.features.public_fields

    def test_feature_flag_can_be_toggled(self):
        """Test that the feature flag can be enabled and disabled."""
        self.plan.features.enable_community_engagement = False
        self.plan.features.save()
        self.plan.features.refresh_from_db()
        assert self.plan.features.enable_community_engagement is False

        self.plan.features.enable_community_engagement = True
        self.plan.features.save()
        self.plan.features.refresh_from_db()
        assert self.plan.features.enable_community_engagement is True


class TestPledgeActionRelationship:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_pledge_can_have_multiple_actions(self):
        """Test that a pledge can be associated with multiple actions."""
        action1 = ActionFactory.create(plan=self.plan)
        action2 = ActionFactory.create(plan=self.plan)
        action3 = ActionFactory.create(plan=self.plan)

        pledge = PledgeFactory.create(plan=self.plan, actions=[action1, action2, action3])

        assert set(pledge.actions.all()) == {action1, action2, action3}

    def test_action_can_be_in_multiple_pledges(self):
        """Test that an action can be associated with multiple pledges."""
        action = ActionFactory.create(plan=self.plan)

        pledge1 = PledgeFactory.create(plan=self.plan, actions=[action])
        pledge2 = PledgeFactory.create(plan=self.plan, actions=[action])

        assert action in pledge1.actions.all()
        assert action in pledge2.actions.all()

    def test_pledge_actions_unique_together(self):
        """Test that the same action cannot be added twice to the same pledge."""
        action = ActionFactory.create(plan=self.plan)
        pledge = PledgeFactory.create(plan=self.plan)

        # Add action first time
        pledge.actions.add(action)
        assert pledge.actions.count() == 1

        # Adding same action again should not create duplicate
        pledge.actions.add(action)
        assert pledge.actions.count() == 1


class TestPledgeOrdering:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_pledge_ordering_by_plan_and_order(self):
        """Test that pledges are ordered by plan and then by order field."""
        pledge3 = PledgeFactory.create(plan=self.plan, order=3)
        pledge1 = PledgeFactory.create(plan=self.plan, order=1)
        pledge2 = PledgeFactory.create(plan=self.plan, order=2)

        # Use explicit order_by to verify ordering
        pledges = list(Pledge.objects.filter(plan=self.plan).order_by('order'))

        assert pledges == [pledge1, pledge2, pledge3]
        assert pledges[0].order == 1
        assert pledges[1].order == 2
        assert pledges[2].order == 3

    def test_pledge_order_can_be_changed(self):
        """Test that pledge order can be modified."""
        pledge = PledgeFactory.create(plan=self.plan, order=1)

        pledge.order = 5
        pledge.save()
        pledge.refresh_from_db()

        assert pledge.order == 5


@pytest.mark.django_db
class TestPledgeQuerySet:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_for_plan_filters_by_plan(self):
        """Test that for_plan queryset method filters by plan."""
        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()

        pledge1 = PledgeFactory.create(plan=self.plan)
        pledge2 = PledgeFactory.create(plan=other_plan)

        qs = Pledge.objects.for_plan(self.plan)

        assert pledge1 in qs
        assert pledge2 not in qs

    def test_visible_for_user_filters_by_plan(self):
        """Test that visible_for_user queryset method filters by plan."""
        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()

        pledge1 = PledgeFactory.create(plan=self.plan)
        pledge2 = PledgeFactory.create(plan=other_plan)

        # Using anonymous user since all pledges are currently visible to all users
        qs = Pledge.objects.visible_for_user(AnonymousUser(), self.plan)

        assert pledge1 in qs
        assert pledge2 not in qs


class TestPledgeOptionalFields:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_pledge_with_minimal_fields(self):
        """Test that a pledge can be created with only required fields."""
        pledge = Pledge.objects.create(
            plan=self.plan,
            name='Minimal Pledge',
            slug='minimal-pledge',
        )

        assert pledge.name == 'Minimal Pledge'
        assert pledge.description == ''
        assert pledge.resident_count is None
        assert pledge.impact_statement == ''
        assert pledge.local_equivalency == ''
        assert pledge.image is None

    def test_pledge_with_empty_body(self):
        """Test that a pledge can have an empty StreamField body."""
        pledge = Pledge.objects.create(
            plan=self.plan,
            name='Empty Body Pledge',
            slug='empty-body-pledge',
        )

        # StreamField body should be empty/None by default
        assert pledge.body is None or len(pledge.body) == 0

    def test_pledge_uuid_is_auto_generated(self):
        """Test that UUID is automatically generated for new pledges."""
        pledge = Pledge.objects.create(
            plan=self.plan,
            name='UUID Test Pledge',
            slug='uuid-test-pledge',
        )

        assert pledge.uuid is not None
        # UUID should be unique
        pledge2 = Pledge.objects.create(
            plan=self.plan,
            name='UUID Test Pledge 2',
            slug='uuid-test-pledge-2',
        )
        assert pledge.uuid != pledge2.uuid
        # Test that it's in public_fields
        assert 'enable_community_engagement' in self.plan.features.public_fields


class TestPledgeUser:
    """Tests for the PledgeUser model."""

    def test_pledge_user_creation(self):
        """Test that a PledgeUser can be created with auto-generated UUID."""
        pledge_user = PledgeUser.objects.create()

        assert pledge_user.uuid is not None
        assert isinstance(pledge_user.uuid, uuid.UUID)
        assert pledge_user.user_data == {}

    def test_pledge_user_with_user_data(self):
        """Test that a PledgeUser can store freeform user data."""
        user_data = {'zip_code': '12345', 'city': 'Test City'}
        pledge_user = PledgeUser.objects.create(user_data=user_data)

        assert pledge_user.user_data == user_data

    def test_pledge_user_uuid_unique(self):
        """Test that each PledgeUser gets a unique UUID."""
        user1 = PledgeUser.objects.create()
        user2 = PledgeUser.objects.create()

        assert user1.uuid != user2.uuid

    def test_pledge_user_str(self):
        """Test the string representation of PledgeUser."""
        pledge_user = PledgeUser.objects.create()

        assert str(pledge_user) == str(pledge_user.uuid)


class TestPledgeCommitment:
    """Tests for the PledgeCommitment model."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = PlanFactory.create()
        self.pledge = Pledge.objects.create(
            plan=self.plan,
            name='Test Pledge',
            slug='test-pledge',
        )
        self.pledge_user = PledgeUser.objects.create()

    def test_pledge_commitment_creation(self):
        """Test that a PledgeCommitment can be created."""
        commitment = PledgeCommitment.objects.create(
            pledge=self.pledge,
            pledge_user=self.pledge_user,
        )

        assert commitment.pledge == self.pledge
        assert commitment.pledge_user == self.pledge_user
        assert commitment.created_at is not None

    def test_pledge_commitment_unique_together(self):
        """Test that a user can only commit to a pledge once."""
        from django.db import IntegrityError

        PledgeCommitment.objects.create(
            pledge=self.pledge,
            pledge_user=self.pledge_user,
        )

        with pytest.raises(IntegrityError):
            PledgeCommitment.objects.create(
                pledge=self.pledge,
                pledge_user=self.pledge_user,
            )

    def test_pledge_commitment_user_can_commit_to_multiple_pledges(self):
        """Test that a user can commit to multiple different pledges."""
        pledge2 = Pledge.objects.create(
            plan=self.plan,
            name='Second Pledge',
            slug='second-pledge',
        )

        commitment1 = PledgeCommitment.objects.create(
            pledge=self.pledge,
            pledge_user=self.pledge_user,
        )
        commitment2 = PledgeCommitment.objects.create(
            pledge=pledge2,
            pledge_user=self.pledge_user,
        )

        assert commitment1.pledge != commitment2.pledge
        assert self.pledge_user.commitments.count() == 2

    def test_pledge_commitment_str(self):
        """Test the string representation of PledgeCommitment."""
        commitment = PledgeCommitment.objects.create(
            pledge=self.pledge,
            pledge_user=self.pledge_user,
        )

        assert str(self.pledge_user.uuid) in str(commitment)
        assert self.pledge.name in str(commitment)
