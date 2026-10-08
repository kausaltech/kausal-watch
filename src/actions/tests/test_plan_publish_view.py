"""
Tests for publishing a plan, which switches its production surface on.

Publishing is the common way a plan goes live, and a plan that goes live is almost always meant
to be readable by anyone, so confirming a publish also sets its visibility to public. Keeping a
plan internal through launch — a site every visitor must sign in to — stays possible, but only
by asking for it on the confirmation screen.

Unpublishing is the mirror image: it takes the production site down and leaves visibility alone,
since a public plan's data was never gated on its launch. Restricting it as well is offered, but
only done when asked for.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from django.contrib.staticfiles import finders
from django.urls import reverse
from django.utils import timezone

import pytest

from aplans.utils import RestrictedVisibilityModel

from actions.models import Plan
from actions.models.plan import PlanDomain, PublicationStatus
from actions.tests.factories import PlanDomainFactory, PlanFactory
from actions.tests.test_change_log_graphql import make_plan_admin
from actions.wagtail_admin import LiveStateColumn, PlanPublishView

pytestmark = pytest.mark.django_db

INTERNAL = RestrictedVisibilityModel.VisibilityState.INTERNAL
PUBLIC = RestrictedVisibilityModel.VisibilityState.PUBLIC


@pytest.fixture
def superuser_client(client, user_factory):
    client.force_login(user_factory(is_superuser=True))
    return client


def _admin_page(client, plan: Plan, url: str) -> str:
    """Render an admin page as a superuser who administers `plan`, which the admin chrome needs."""
    user = make_plan_admin(plan)
    user.is_superuser = True
    user.save(update_fields=['is_superuser'])
    client.force_login(user)
    return client.get(url).content.decode()


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

    def test_unpublishing_can_make_the_plan_internal_when_asked(self, superuser_client, plan_factory):
        """Taking the production site down leaves preview hosts and the API serving a public plan."""
        plan = plan_factory(visibility=PUBLIC, published_at=timezone.now() - timedelta(minutes=5))

        superuser_client.post(_unpublish_url(plan), data={'make_internal': 'on'})

        plan.refresh_from_db()
        assert not plan.is_live()
        assert plan.visibility == INTERNAL

    def test_unpublishing_a_public_plan_says_it_stays_readable(self, client, plan_factory):
        plan = plan_factory(visibility=PUBLIC, published_at=timezone.now() - timedelta(minutes=5))

        content = _admin_page(client, plan, _unpublish_url(plan))

        assert 'inaccessible to the public' not in content
        assert 'The plan stays public' in content
        assert 'name="make_internal"' in content

    def test_unpublishing_an_internal_plan_offers_nothing_more(self, client, plan_factory):
        plan = plan_factory(visibility=INTERNAL, published_at=timezone.now() - timedelta(minutes=5))

        content = _admin_page(client, plan, _unpublish_url(plan))

        assert 'The plan stays public' not in content
        assert 'name="make_internal"' not in content


class TestPublishConfirmationAddresses:
    """
    The confirmation lists exactly the addresses that publishing will launch.

    It has to agree with `PlanDomain.is_launched`, or the screen a superuser reads before making a
    site public describes a different set of hostnames than the one that goes live.
    """

    def test_a_domain_with_no_environment_counts_as_production(self, client, plan_factory):
        plan = plan_factory(published_at=None)
        PlanDomainFactory.create(plan=plan, hostname='legacy.example.org', deployment_environment='')

        content = _admin_page(client, plan, _publish_url(plan))

        assert 'https://legacy.example.org' in content
        assert 'no production domains have been configured' not in content

    def test_preview_domains_are_not_listed(self, client, plan_factory):
        plan = plan_factory(published_at=None)
        PlanDomainFactory.create(
            plan=plan, hostname='preview.example.org', deployment_environment=PlanDomain.DeploymentEnvironment.PREVIEW
        )

        content = _admin_page(client, plan, _publish_url(plan))

        # The warning names it as where the plan's links will point, but not as a production address.
        assert '<li><strong><a href="https://preview.example.org"' not in content
        assert 'because no production domains have been configured' in content

    def test_the_base_path_is_part_of_the_address(self, client, plan_factory):
        """On a multi-plan site the hostname alone points at another plan."""
        plan = plan_factory(published_at=None)
        PlanDomainFactory.create(
            plan=plan,
            hostname='shared.example.org',
            base_path='/this-plan',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )

        content = _admin_page(client, plan, _publish_url(plan))

        assert 'https://shared.example.org/this-plan' in content

    def test_a_domain_held_back_by_its_override_is_not_listed(self, client, plan_factory):
        """The per-domain override keeps that hostname dark whatever the plan's launch state."""
        plan = plan_factory(published_at=None)
        PlanDomainFactory.create(
            plan=plan,
            hostname='held.example.org',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
            publication_status_override=PublicationStatus.UNPUBLISHED,
        )

        content = _admin_page(client, plan, _publish_url(plan))

        assert 'https://held.example.org' not in content


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

    @pytest.mark.parametrize(
        'published_at_offset',
        [timedelta(minutes=-5), None, timedelta(days=1)],
        ids=['live', 'not-live', 'scheduled'],
    )
    def test_the_plan_listing_colours_every_state(self, plan_factory, published_at_offset):
        published_at = timezone.now() + published_at_offset if published_at_offset is not None else None
        plan = plan_factory(published_at=published_at)

        status_class = LiveStateColumn().get_cell_context_data(plan, {'row': None, 'table': None})['status_class']

        stylesheet = finders.find('css/admin-styles.css')
        assert isinstance(stylesheet, str)
        assert f'.{status_class} {{' in Path(stylesheet).read_text(encoding='utf-8')


def _preview_url(plan: Plan) -> str | None:
    view = PlanPublishView()
    view.object = plan
    return view.get_preview_url()


class TestPreviewURL:
    """The address the publish confirmation shows when a plan has no production domains."""

    @pytest.fixture
    def unpublished_plan(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
        return PlanFactory.create(identifier='myplan', primary_language='en', published_at=None)

    def test_shows_the_wildcard_address_without_domains(self, unpublished_plan):
        assert _preview_url(unpublished_plan) == 'https://myplan.example.com'

    def test_shows_the_preview_domain_links_will_use(self, unpublished_plan):
        PlanDomainFactory.create(
            plan=unpublished_plan,
            hostname='preview.city.gov',
            base_path='/climate',
            deployment_environment=PlanDomain.DeploymentEnvironment.PREVIEW,
        )
        assert _preview_url(unpublished_plan) == 'https://preview.city.gov/climate'

    def test_falls_back_to_localhost_in_development(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['localhost']
        settings.DEPLOYMENT_TYPE = 'development'
        plan = PlanFactory.create(identifier='myplan', primary_language='en', published_at=None)
        assert _preview_url(plan) == 'http://myplan.localhost'

    def test_is_none_when_no_address_can_be_resolved(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['localhost']
        settings.DEPLOYMENT_TYPE = 'production'
        plan = PlanFactory.create(identifier='myplan', primary_language='en', published_at=None)
        assert _preview_url(plan) is None
