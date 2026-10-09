from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import pytest

from actions.models.features import PlanFeatures
from actions.models.plan import PlanDomain
from actions.tests.factories import ActionFactory, PlanDomainFactory
from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory
from pages.models import StaticPage

if TYPE_CHECKING:
    from actions.models import Plan

pytestmark = pytest.mark.django_db

ACTION_COUNT = 5


def _domain_query_count(ctx: CaptureQueriesContext) -> int:
    return sum(1 for q in ctx.captured_queries if 'actions_plandomain' in q['sql'])


@pytest.fixture
def live_plan_with_domain(plan_with_pages: Plan, settings) -> Plan:
    plan = plan_with_pages
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
    type(plan).objects.filter(pk=plan.pk).update(published_at=timezone.now() - timedelta(days=1))
    PlanDomainFactory.create(
        plan=plan, hostname='custom.city.gov', deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION
    )
    return plan


@pytest.mark.parametrize(
    'query',
    [
        pytest.param('query($plan: ID!) { planActions(plan: $plan) { viewUrl } }', id='planActions'),
        pytest.param(
            'query($plan: ID!) { planActions(plan: $plan) { viewUrl(clientUrl: "https://custom.city.gov") } }',
            id='planActions-clientUrl',
        ),
        pytest.param('query($plan: ID!) { planActions(plan: $plan) { exportPdf { url } } }', id='planActions-exportPdf'),
        pytest.param('query($plan: ID!) { plan(id: $plan) { actions { viewUrl } } }', id='plan-actions'),
    ],
)
def test_action_listing_looks_up_domains_once(live_plan_with_domain, graphql_client_query_data, query):
    plan = live_plan_with_domain
    for _ in range(ACTION_COUNT):
        ActionFactory.create(plan=plan)
    PlanFeatures.objects.filter(plan=plan).update(enable_action_pdf_export_in_public_ui=True)
    with CaptureQueriesContext(connection) as ctx:
        data = graphql_client_query_data(query, variables=dict(plan=plan.identifier))
    actions = data['planActions'] if 'planActions' in data else data['plan']['actions']
    assert len(actions) == ACTION_COUNT
    assert all(action.get('viewUrl') or action.get('exportPdf') for action in actions)
    assert _domain_query_count(ctx) <= 1


@pytest.mark.parametrize('client_url', [None, 'https://custom.city.gov'])
def test_indicator_listing_looks_up_plan_domains_once(live_plan_with_domain, graphql_client_query_data, client_url):
    plan = live_plan_with_domain
    for _ in range(ACTION_COUNT):
        IndicatorLevelFactory.create(indicator=IndicatorFactory.create(organization=plan.organization), plan=plan)
    view_url = f'viewUrl(clientUrl: "{client_url}")' if client_url else 'viewUrl'
    query = 'query($plan: ID!) { planIndicators(plan: $plan) { plans { VIEW_URL } } }'.replace('VIEW_URL', view_url)
    with CaptureQueriesContext(connection) as ctx:
        data = graphql_client_query_data(query, variables=dict(plan=plan.identifier))
    assert len(data['planIndicators']) == ACTION_COUNT
    assert all(p['viewUrl'] == 'https://custom.city.gov' for ind in data['planIndicators'] for p in ind['plans'])
    assert _domain_query_count(ctx) <= 1


@pytest.mark.parametrize('client_url', [None, 'https://custom.city.gov'])
def test_menu_items_do_not_look_up_the_plan_per_item(live_plan_with_domain, graphql_client_query_data, client_url):
    plan = live_plan_with_domain
    view_url = f'viewUrl(clientUrl: "{client_url}")' if client_url else 'viewUrl'
    query = """
        query($plan: ID!) {
          plan(id: $plan) { mainMenu { items(withDescendants: false) { ... on PageMenuItem { VIEW_URL } } } }
        }
    """.replace('VIEW_URL', view_url)

    def count_queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            data = graphql_client_query_data(query, variables=dict(plan=plan.identifier))
        assert all(item['viewUrl'] == 'https://custom.city.gov' for item in data['plan']['mainMenu']['items'])
        return len(ctx.captured_queries)

    plan.root_page.add_child(instance=StaticPage(title='Page 0', show_in_menus=True))
    one_item = count_queries()
    for i in range(1, ACTION_COUNT):
        plan.root_page.add_child(instance=StaticPage(title=f'Page {i}', show_in_menus=True))
    assert count_queries() == one_item


def test_export_pdf_reads_plan_features_from_the_plan_cache(live_plan_with_domain, graphql_client_query_data):
    plan = live_plan_with_domain
    for _ in range(ACTION_COUNT):
        ActionFactory.create(plan=plan)
    PlanFeatures.objects.filter(plan=plan).update(enable_action_pdf_export_in_public_ui=True)
    query = 'query($plan: ID!) { planActions(plan: $plan) { exportPdf { url } } }'
    with CaptureQueriesContext(connection) as ctx:
        data = graphql_client_query_data(query, variables=dict(plan=plan.identifier))
    assert all(action['exportPdf'] for action in data['planActions'])
    # The action query itself must not join the plan and its features; the plan cache has them.
    action_queries = [q['sql'] for q in ctx.captured_queries if 'FROM "actions_action"' in q['sql']]
    assert action_queries
    assert not any('actions_planfeatures' in sql for sql in action_queries)


def test_export_pdf_is_null_when_plan_url_unresolvable(plan, graphql_client_query_data, settings):
    ActionFactory.create(plan=plan)
    PlanFeatures.objects.filter(plan=plan).update(enable_action_pdf_export_in_public_ui=True)
    settings.HOSTNAME_PLAN_DOMAINS = ['localhost']
    settings.DEPLOYMENT_TYPE = 'production'
    plan.domains.all().delete()
    query = 'query($plan: ID!) { planActions(plan: $plan) { exportPdf { url } } }'
    data = graphql_client_query_data(query, variables=dict(plan=plan.identifier))
    assert data['planActions']
    assert all(action['exportPdf'] is None for action in data['planActions'])
