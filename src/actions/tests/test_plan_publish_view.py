"""Tests for the address the publish confirmation shows when a plan has no production domains."""

from __future__ import annotations

import pytest

from actions.models.plan import PlanDomain
from actions.tests.factories import PlanDomainFactory, PlanFactory
from actions.wagtail_admin import PlanPublishView

pytestmark = pytest.mark.django_db


def _preview_url(plan) -> str | None:
    view = PlanPublishView()
    view.object = plan
    return view.get_preview_url()


@pytest.fixture
def unpublished_plan(settings):
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
    return PlanFactory.create(identifier='myplan', primary_language='en', published_at=None)


def test_shows_the_wildcard_address_without_domains(unpublished_plan):
    assert _preview_url(unpublished_plan) == 'https://myplan.example.com'


def test_shows_the_preview_domain_links_will_use(unpublished_plan):
    PlanDomainFactory.create(
        plan=unpublished_plan,
        hostname='preview.city.gov',
        base_path='/climate',
        deployment_environment=PlanDomain.DeploymentEnvironment.PREVIEW,
    )
    assert _preview_url(unpublished_plan) == 'https://preview.city.gov/climate'


def test_falls_back_to_localhost_in_development(settings):
    settings.HOSTNAME_PLAN_DOMAINS = ['localhost']
    settings.DEPLOYMENT_TYPE = 'development'
    plan = PlanFactory.create(identifier='myplan', primary_language='en', published_at=None)
    assert _preview_url(plan) == 'http://myplan.localhost'


def test_is_none_when_no_address_can_be_resolved(settings):
    settings.HOSTNAME_PLAN_DOMAINS = ['localhost']
    settings.DEPLOYMENT_TYPE = 'production'
    plan = PlanFactory.create(identifier='myplan', primary_language='en', published_at=None)
    assert _preview_url(plan) is None
