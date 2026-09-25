"""
Tests for the anonymous GraphQL execution cache.

The cache key assumes a plan's answers change only when something is saved, which bumps
`cache_invalidated_at`. A scheduled launch is the one change that happens without a save: the
publication date simply passes. The key must follow it, or a result cached just before the launch
keeps serving the unlaunched answer for the whole cache lifetime.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

import pytest

from aplans.schema_context import WatchExecutionCacheExtension

from actions.models.plan import Plan, PlanDomain

if TYPE_CHECKING:
    from collections.abc import Generator

pytestmark = pytest.mark.django_db

STATUS_QUERY = """
  query GetPlansByHostname($hostname: String) {
    plansForHostname(hostname: $hostname) {
      domain { status }
    }
  }
"""

LOCMEM_CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-execution-cache',
    },
}


@pytest.fixture
def cache_hits(settings, monkeypatch) -> Generator[list[bool]]:
    """Run against a real cache, and record whether each lookup was a hit."""
    settings.CACHES = LOCMEM_CACHES
    from django.core.cache import cache

    hits: list[bool] = []
    original = WatchExecutionCacheExtension.get_from_cache

    def get_from_cache(self, key):
        result = original(self, key)
        hits.append(result is not None)
        return result

    monkeypatch.setattr(WatchExecutionCacheExtension, 'get_from_cache', get_from_cache)
    cache.clear()
    yield hits
    cache.clear()


def test_scheduled_launch_is_not_hidden_by_cached_result(
    cache_hits, graphql_client_query_data, plan_factory, plan_domain_factory
):
    plan = plan_factory(visibility='public', published_at=timezone.now() + timedelta(hours=1))
    domain = plan_domain_factory(plan=plan, deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION)
    headers = {'X-Cache-Plan-Identifier': plan.identifier}

    def status() -> str:
        data = graphql_client_query_data(STATUS_QUERY, variables={'hostname': domain.hostname}, headers=headers)
        return data['plansForHostname'][0]['domain']['status']

    assert status() == 'UNAVAILABLE'

    # The date passing, as opposed to somebody saving the plan: `update` leaves
    # `cache_invalidated_at` alone, exactly as the clock does.
    Plan.objects.filter(pk=plan.pk).update(published_at=timezone.now() - timedelta(minutes=1))

    assert status() == 'AVAILABLE'
    assert cache_hits == [False, False]


def test_unchanged_plan_is_served_from_cache(cache_hits, graphql_client_query_data, plan_factory, plan_domain_factory):
    plan = plan_factory(visibility='public', published_at=timezone.now() + timedelta(hours=1))
    domain = plan_domain_factory(plan=plan, deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION)
    headers = {'X-Cache-Plan-Identifier': plan.identifier}

    def status() -> str:
        data = graphql_client_query_data(STATUS_QUERY, variables={'hostname': domain.hostname}, headers=headers)
        return data['plansForHostname'][0]['domain']['status']

    assert status() == 'UNAVAILABLE'
    # Anything that does not change liveness must still hit the cache, or the key has
    # started varying on something it should not.
    Plan.objects.filter(pk=plan.pk).update(published_at=timezone.now() + timedelta(hours=2))

    assert status() == 'UNAVAILABLE'
    assert cache_hits == [False, True]
