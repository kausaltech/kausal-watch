"""
Tests for publishing a plan, which switches its production surface on.

Publishing is the common way a plan goes live, and a plan that goes live is almost always meant
to be readable by anyone, so confirming a publish also sets its visibility to public. Keeping a
plan internal through launch — a site every visitor must sign in to — stays possible, but only
by asking for it on the confirmation screen.
"""

from __future__ import annotations

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

import pytest

from aplans.utils import RestrictedVisibilityModel

from actions.models import Plan

pytestmark = pytest.mark.django_db

INTERNAL = RestrictedVisibilityModel.VisibilityState.INTERNAL
PUBLIC = RestrictedVisibilityModel.VisibilityState.PUBLIC


@pytest.fixture
def superuser_client(client, user_factory):
    client.force_login(user_factory(is_superuser=True))
    return client


def _publish_url(plan: Plan) -> str:
    return reverse('wagtailsnippets_actions_plan:publish', kwargs={'pk': plan.pk})


def _unpublish_url(plan: Plan) -> str:
    return reverse('wagtailsnippets_actions_plan:unpublish', kwargs={'pk': plan.pk})


class TestPublishing:
    def test_publishing_makes_the_plan_public(self, superuser_client, plan_factory):
        plan = plan_factory(visibility=INTERNAL, published_at=None)

        superuser_client.post(_publish_url(plan))

        plan.refresh_from_db()
        assert plan.is_live()
        assert plan.visibility == PUBLIC

    def test_publishing_can_keep_the_plan_internal_when_asked(self, superuser_client, plan_factory):
        """The rare site that launches but still requires everyone to sign in."""
        plan = plan_factory(visibility=INTERNAL, published_at=None)

        superuser_client.post(_publish_url(plan), data={'keep_internal': 'on'})

        plan.refresh_from_db()
        assert plan.is_live()
        assert plan.visibility == INTERNAL

    def test_unpublishing_leaves_visibility_alone(self, superuser_client, plan_factory):
        """
        Taking a site down does not re-restrict the data.

        The two are independent, and silently narrowing access on the way down would be a
        bigger action than the button claims.
        """
        plan = plan_factory(visibility=PUBLIC, published_at=timezone.now() - timedelta(minutes=5))

        superuser_client.post(_unpublish_url(plan))

        plan.refresh_from_db()
        assert not plan.is_live()
        assert plan.visibility == PUBLIC


class TestLiveState:
    """The launch axis is named for the site, so it shares no word with the visibility axis."""

    def test_a_launched_plan_is_live(self, plan_factory):
        plan = plan_factory(published_at=timezone.now() - timedelta(minutes=5))
        assert plan.live_state == Plan.LiveState.LIVE

    def test_a_plan_that_never_launched_is_not_live(self, plan_factory):
        plan = plan_factory(published_at=None)
        assert plan.live_state == Plan.LiveState.NOT_LIVE

    def test_a_future_date_is_scheduled(self, plan_factory):
        plan = plan_factory(published_at=timezone.now() + timedelta(days=1))
        assert plan.live_state == Plan.LiveState.SCHEDULED

    @pytest.mark.parametrize(
        ('state', 'label'),
        [
            (Plan.LiveState.LIVE, 'Live'),
            (Plan.LiveState.NOT_LIVE, 'Not live'),
            (Plan.LiveState.SCHEDULED, 'Scheduled'),
        ],
    )
    def test_labels_share_no_word_with_the_visibility_axis(self, state, label):
        assert str(state.label) == label
        visibility_labels = {str(choice.label) for choice in RestrictedVisibilityModel.VisibilityState}
        assert str(state.label) not in visibility_labels
