"""
Tests for Plan admin IsActiveFilter.

This module tests the custom IsActiveFilter used in the Wagtail admin
to filter plans by active status.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from actions.models import Plan
from actions.tests.factories import PlanFactory
from actions.wagtail_admin import IsActiveFilter, PlanIndexView, PlanViewSet
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


class TestIsActiveFilter:
    """Test the IsActiveFilter used in plan admin."""

    def test_filter_defaults_to_active_plans(self):
        """Test that the filter defaults to showing only active plans."""
        active_plan = PlanFactory.create(is_active=True)
        inactive_plan = PlanFactory.create(is_active=False)

        filter_instance = IsActiveFilter()
        # When no value is provided (default case), it should filter to active only
        filtered_qs = filter_instance.filter(Plan.objects.qs, None)

        assert active_plan in filtered_qs
        assert inactive_plan not in filtered_qs

    def test_filter_active_value(self):
        """Test filtering with 'active' value explicitly selected."""
        active_plan = PlanFactory.create(is_active=True)
        inactive_plan = PlanFactory.create(is_active=False)

        filter_instance = IsActiveFilter()
        filtered_qs = filter_instance.filter(Plan.objects.qs, 'active')

        assert active_plan in filtered_qs
        assert inactive_plan not in filtered_qs

    def test_filter_inactive_value(self):
        """Test filtering with 'inactive' value shows only inactive plans."""
        active_plan = PlanFactory.create(is_active=True)
        inactive_plan = PlanFactory.create(is_active=False)

        filter_instance = IsActiveFilter()
        filtered_qs = filter_instance.filter(Plan.objects.qs, 'inactive')

        assert active_plan not in filtered_qs
        assert inactive_plan in filtered_qs

    def test_filter_all_value(self):
        """Test filtering with 'all' value shows both active and inactive plans."""
        active_plan = PlanFactory.create(is_active=True)
        inactive_plan = PlanFactory.create(is_active=False)

        filter_instance = IsActiveFilter()
        filtered_qs = filter_instance.filter(Plan.objects.qs, 'all')

        assert active_plan in filtered_qs
        assert inactive_plan in filtered_qs

    def test_filter_with_empty_string(self):
        """Test that empty string value defaults to showing active plans."""
        active_plan = PlanFactory.create(is_active=True)
        inactive_plan = PlanFactory.create(is_active=False)

        filter_instance = IsActiveFilter()
        filtered_qs = filter_instance.filter(Plan.objects.qs, '')

        assert active_plan in filtered_qs
        assert inactive_plan not in filtered_qs

    def test_filter_has_correct_choices(self):
        """Test that the filter has the expected choice options."""
        filter_instance = IsActiveFilter()

        # Check that choices are defined correctly
        assert hasattr(filter_instance, 'extra')
        choices = filter_instance.extra.get('choices', [])

        # Should have 'active', 'all', and 'inactive' choices
        choice_values = [c[0] for c in choices]
        assert 'active' in choice_values
        assert 'all' in choice_values
        assert 'inactive' in choice_values

    def test_filter_has_no_empty_label(self):
        """Test that the filter does not have an empty label (no unselected option)."""
        filter_instance = IsActiveFilter()

        # empty_label should be None to prevent an unselected state
        assert filter_instance.extra.get('empty_label') is None


class TestPlanFilterVisibility:
    """Test that the is_active filter is shown only to superusers."""

    def test_superuser_gets_filter_with_active_status(self, superuser):
        """Test that superusers get the filterset with is_active filter."""
        viewset = PlanViewSet()
        view = PlanIndexView(**viewset.get_index_view_kwargs())
        view.request = Mock()
        view.request.user = superuser

        filterset = view.filterset_class(**view.get_filterset_kwargs())
        assert 'is_active' in filterset.filters

    def test_non_superuser_gets_base_filter(self):
        """Test that non-superusers get the base filterset without is_active filter."""
        user = UserFactory.create()

        viewset = PlanViewSet()
        view = PlanIndexView(**viewset.get_index_view_kwargs())
        view.request = Mock()
        view.request.user = user

        filterset = view.filterset_class(**view.get_filterset_kwargs())
        assert 'is_active' not in filterset.filters

    def test_non_superuser_sees_only_active_plans_by_default(self):
        """Test that non-superusers only see active plans in the queryset by default."""
        user = UserFactory.create()
        active_plan = PlanFactory.create(is_active=True)
        inactive_plan = PlanFactory.create(is_active=False)

        # Mock get_adminable_plans to return both plans
        user.get_adminable_plans = Mock(return_value=Plan.objects.qs.filter(  # type: ignore[method-assign]
            id__in=[active_plan.id, inactive_plan.id]
        ))

        mock_request = Mock()
        mock_request.user = user

        viewset = PlanViewSet()
        qs = viewset.get_queryset(mock_request)

        assert qs is not None
        assert active_plan in qs
        assert inactive_plan not in qs

    def test_superuser_sees_all_plans_by_default(self, superuser):
        """Test that superusers see all plans (both active and inactive) in the queryset."""
        active_plan = PlanFactory.create(is_active=True)
        inactive_plan = PlanFactory.create(is_active=False)

        # Mock get_adminable_plans to return both plans
        superuser.get_adminable_plans = Mock(return_value=Plan.objects.qs.filter(
            id__in=[active_plan.id, inactive_plan.id]
        ))

        mock_request = Mock()
        mock_request.user = superuser

        viewset = PlanViewSet()
        qs = viewset.get_queryset(mock_request)

        # Superusers should see all plans (they'll use the filter to narrow down)
        assert qs is not None
        assert active_plan in qs
        assert inactive_plan in qs
