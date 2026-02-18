"""
Tests for Plan.is_active field and related functionality.

This module tests the is_active field on the Plan model and its effects on:
- Plan querysets
- Permission checking
- Admin filtering
"""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

import pytest

from actions.models import Plan
from actions.permission_policy import PlanPermissionPolicy

pytestmark = pytest.mark.django_db


class TestPlanQuerySet:
    """Test Plan queryset methods respect is_active field."""

    def test_live_queryset_excludes_inactive_plans(self, plan_factory):
        """Test that Plan.objects.live() excludes inactive plans."""
        active_plan = plan_factory(is_active=True, published_at=timezone.now())
        inactive_plan = plan_factory(is_active=False, published_at=timezone.now())

        live_plans = Plan.objects.qs.live()

        assert active_plan in live_plans
        assert inactive_plan not in live_plans

    def test_live_queryset_includes_all_conditions(self, plan_factory):
        """Test that live() checks published_at, archived_at, and is_active."""
        # Active and published
        live_plan = plan_factory(
            is_active=True,
            published_at=timezone.now() - timedelta(days=1),
            archived_at=None,
        )

        # Inactive
        inactive_plan = plan_factory(
            is_active=False,
            published_at=timezone.now() - timedelta(days=1),
            archived_at=None,
        )

        # Not published yet
        unpublished_plan = plan_factory(
            is_active=True,
            published_at=None,
            archived_at=None,
        )

        # Archived
        archived_plan = plan_factory(
            is_active=True,
            published_at=timezone.now() - timedelta(days=1),
            archived_at=timezone.now(),
        )

        live_plans = Plan.objects.qs.live()

        assert live_plan in live_plans
        assert inactive_plan not in live_plans
        assert unpublished_plan not in live_plans
        assert archived_plan not in live_plans

    def test_available_for_request_excludes_inactive_plans(self, plan_factory, rf):
        """Test that available_for_request() excludes inactive plans."""
        active_plan = plan_factory(is_active=True, published_at=timezone.now())
        inactive_plan = plan_factory(is_active=False, published_at=timezone.now())

        request = rf.get('/')
        request.user = AnonymousUser()

        available_plans = Plan.objects.qs.available_for_request(request)

        assert active_plan in available_plans
        assert inactive_plan not in available_plans


class TestPlanPermissionPolicy:
    """Test PlanPermissionPolicy respects is_active field."""

    def test_anonymous_cannot_view_inactive_plan(self, plan_factory):
        """Test that anonymous users cannot view inactive plans."""
        inactive_plan = plan_factory(is_active=False, published_at=timezone.now())
        policy = PlanPermissionPolicy(Plan)

        has_perm = policy.anon_has_perm('view', inactive_plan)

        assert has_perm is False

    def test_anonymous_can_view_active_plan(self, plan_factory):
        """Test that anonymous users can view active published plans."""
        active_plan = plan_factory(
            is_active=True,
            published_at=timezone.now() - timedelta(days=1),
        )
        # Ensure expose_unpublished_plan_only_to_authenticated_user is False
        active_plan.features.expose_unpublished_plan_only_to_authenticated_user = False
        active_plan.features.save()

        policy = PlanPermissionPolicy(Plan)

        has_perm = policy.anon_has_perm('view', active_plan)

        assert has_perm is True

    def test_construct_perm_q_anon_excludes_inactive_plans(self, plan_factory):
        """Test that anonymous user query filters exclude inactive plans."""
        active_plan = plan_factory(is_active=True, published_at=timezone.now())
        inactive_plan = plan_factory(is_active=False, published_at=timezone.now())

        policy = PlanPermissionPolicy(Plan)
        q = policy.construct_perm_q_anon('view')

        assert q is not None
        filtered_plans = Plan.objects.filter(q)

        assert active_plan in filtered_plans or not active_plan.features.expose_unpublished_plan_only_to_authenticated_user
        assert inactive_plan not in filtered_plans

    def test_superuser_can_view_inactive_plan(self, plan_factory, user_factory):
        """Test that superusers can view inactive plans."""
        inactive_plan = plan_factory(is_active=False, published_at=timezone.now())
        superuser = user_factory(is_superuser=True)

        policy = PlanPermissionPolicy(Plan)

        has_perm = policy.user_has_perm(superuser, 'view', inactive_plan)

        assert has_perm is True

    def test_non_superuser_cannot_view_inactive_plan(self, plan_factory, user_factory):
        """Test that non-superusers cannot view inactive plans they don't admin."""
        inactive_plan = plan_factory(is_active=False, published_at=timezone.now())
        regular_user = user_factory(is_superuser=False, is_staff=True)

        policy = PlanPermissionPolicy(Plan)

        has_perm = policy.user_has_perm(regular_user, 'view', inactive_plan)

        assert has_perm is False

    def test_filter_by_perm_excludes_inactive_for_anon(self, plan_factory):
        """Test that visible_for_user() excludes inactive plans for anonymous users."""
        active_plan = plan_factory(is_active=True, published_at=timezone.now())
        inactive_plan = plan_factory(is_active=False, published_at=timezone.now())

        # Ensure expose flag is False so they're viewable when active
        for p in [active_plan, inactive_plan]:
            p.features.expose_unpublished_plan_only_to_authenticated_user = False
            p.features.save()

        anon_user = AnonymousUser()
        visible_plans = Plan.objects.qs.visible_for_user(anon_user)

        assert active_plan in visible_plans
        assert inactive_plan not in visible_plans

    def test_filter_by_perm_excludes_inactive_for_regular_user(
        self, plan_factory, user_factory, person_factory
    ):
        """Test that visible_for_user() excludes inactive plans for non-superusers."""
        active_plan = plan_factory(is_active=True, published_at=timezone.now())
        inactive_plan = plan_factory(is_active=False, published_at=timezone.now())

        regular_user = user_factory(is_superuser=False, is_staff=True)
        # Create a person for the user to avoid DoesNotExist error
        person = person_factory()
        regular_user.person = person
        regular_user.save()

        visible_plans = Plan.objects.qs.visible_for_user(regular_user)

        # Regular user should see active plan if published
        assert active_plan in visible_plans or active_plan.features.expose_unpublished_plan_only_to_authenticated_user
        # Regular user should not see inactive plan
        assert inactive_plan not in visible_plans

    def test_filter_by_perm_includes_inactive_for_superuser(
        self, plan_factory, user_factory
    ):
        """Test that visible_for_user() includes inactive plans for superusers."""
        active_plan = plan_factory(is_active=True, published_at=timezone.now())
        inactive_plan = plan_factory(is_active=False, published_at=timezone.now())

        superuser = user_factory(is_superuser=True)

        visible_plans = Plan.objects.qs.visible_for_user(superuser)

        assert active_plan in visible_plans
        assert inactive_plan in visible_plans
