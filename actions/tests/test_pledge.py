from __future__ import annotations

import pytest

from actions.models import Pledge
from actions.tests.factories import PlanFactory


@pytest.mark.django_db
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
            impact_statement='We save <b>100kg CO₂e</b> each year',
            local_equivalency="That's equivalent to <b>10 round trips</b>",
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
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            Pledge.objects.create(
                plan=self.plan,
                name='Second Pledge',
                slug='test-pledge',
            )

    def test_feature_flag(self):
        """Test that feature flag is properly set."""
        assert self.plan.features.enable_community_engagement is True

        # Test that it's in public_fields
        assert 'enable_community_engagement' in self.plan.features.public_fields
