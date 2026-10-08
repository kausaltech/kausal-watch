from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, cast

from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils.timezone import make_aware

import pytest

from actions.models import Plan
from actions.tests.factories import PlanFactory
from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory
from pages.models import ActionListPage
from search.schema import SearchHit, SearchHitObj, SearchResults

if TYPE_CHECKING:
    from aplans.graphql_types import GQLInfo

pytestmark = pytest.mark.django_db


@pytest.fixture
def indicator_shared_between_plans():
    """Link an indicator to an older unpublished plan and to a published one."""
    older_plan = PlanFactory.create(published_at=None)
    searched_plan = PlanFactory.create()
    Plan.objects.filter(pk=older_plan.pk).update(created_at=make_aware(datetime.datetime(2020, 1, 1)))  # noqa: DTZ001
    Plan.objects.filter(pk=searched_plan.pk).update(created_at=make_aware(datetime.datetime(2024, 1, 1)))  # noqa: DTZ001
    indicator = IndicatorFactory.create()
    IndicatorLevelFactory.create(indicator=indicator, plan=older_plan)
    IndicatorLevelFactory.create(indicator=indicator, plan=searched_plan)
    indicator.relevance = 1.0
    return indicator, older_plan, searched_plan


def test_indicator_hit_is_bound_to_a_searched_plan(indicator_shared_between_plans) -> None:
    indicator, older_plan, searched_plan = indicator_shared_between_plans
    assert indicator.plans.first() == older_plan

    hits = SearchResults.resolve_hits({'hits': [indicator], 'plan_ids': [searched_plan.pk]}, cast('GQLInfo', None))

    assert [hit.plan for hit in hits] == [searched_plan]


def test_indicator_hit_outside_the_searched_plans_is_dropped(indicator_shared_between_plans) -> None:
    indicator, _older_plan, _searched_plan = indicator_shared_between_plans

    hits = SearchResults.resolve_hits({'hits': [indicator], 'plan_ids': []}, cast('GQLInfo', None))

    assert hits == []


def test_translated_page_hit_links_to_its_locale(settings, rf) -> None:
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
    plan = PlanFactory.create(identifier='myplan', primary_language='en', other_languages=['fi'])
    plan.create_default_site()
    plan.save()
    fi_page = next(p for p in ActionListPage.objects.filter(locale__language_code='fi') if p.plan == plan)
    request = rf.get('/')
    request.user = AnonymousUser()
    info = cast('GQLInfo', type('Info', (), {'context': request})())
    hit = SearchHitObj(id='page-%d' % fi_page.pk, title=fi_page.title, plan=plan, page=fi_page)

    url = SearchHit.resolve_url(hit, info)

    assert url == 'https://myplan.example.com/fi%s' % fi_page.url_path


def test_page_hit_url_looks_up_plan_domains_once(settings, rf) -> None:
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
    plan = PlanFactory.create(identifier='myplan', primary_language='en')
    plan.create_default_site()
    plan.save()
    page = next(p for p in ActionListPage.objects.all() if p.plan == plan)
    page = ActionListPage.objects.get(pk=page.pk)
    request = rf.get('/')
    request.user = AnonymousUser()
    info = cast('GQLInfo', type('Info', (), {'context': request})())
    hit_plan = page.plan
    assert hit_plan is not None
    hit = SearchHitObj(id='page-%d' % page.pk, title=page.title, plan=hit_plan, page=page)

    with CaptureQueriesContext(connection) as ctx:
        url = SearchHit.resolve_url(hit, info)

    assert url == 'https://myplan.example.com%s' % page.url_path
    assert sum(1 for q in ctx.captured_queries if 'actions_plandomain' in q['sql']) <= 1


def test_page_hit_url_is_none_when_plan_url_unresolvable(settings, rf) -> None:
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
    plan = PlanFactory.create(identifier='myplan', primary_language='en')
    plan.create_default_site()
    plan.save()
    page = next(p for p in ActionListPage.objects.all() if p.plan == plan)
    settings.HOSTNAME_PLAN_DOMAINS = ['localhost']
    settings.DEPLOYMENT_TYPE = 'production'
    request = rf.get('/')
    request.user = AnonymousUser()
    info = cast('GQLInfo', type('Info', (), {'context': request})())
    hit = SearchHitObj(id='page-%d' % page.pk, title=page.title, plan=plan, page=page)

    assert SearchHit.resolve_url(hit, info) is None
