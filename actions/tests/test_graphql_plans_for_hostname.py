from datetime import timedelta

from django.utils import timezone

import pytest

from actions.models.plan import PublicationStatus

pytestmark = pytest.mark.django_db


GET_PLAN_DOMAIN_QUERY = """
  query GetPlansByHostname($hostname: String) {
    plansForHostname(hostname: $hostname) {
      ... on Plan {
        identifier
      }
      domain(hostname: $hostname) {
        hostname
        redirectToHostname
      }
    }
  }
"""

GET_PLANS_BY_HOSTNAME_QUERY = """
  query GetPlansByHostname($hostname: String) {
    plansForHostname(hostname: $hostname) {
      ... on Plan {
        identifier
        id
      }
      domains {
        hostname
        redirectToHostname
        basePath
        status
      }
      primaryLanguage
      publishedAt
    }
  }
"""

GET_PLANS_BY_HOSTNAME_QUERY_STATUSMESSAGE = """
  query GetPlansByHostname($hostname: String) {
    plansForHostname(hostname: $hostname) {
      domains {
        status
        statusMessage
      }
    }
  }
"""


@pytest.mark.parametrize(
    ('publication_status_override', 'delta_minutes', 'expected_publication_status', 'redirect_to'),
    [
        (None, -5, PublicationStatus.PUBLISHED, ''),
        (None, 5, PublicationStatus.SCHEDULED, ''),
        (None, None, PublicationStatus.UNPUBLISHED, ''),
        (PublicationStatus.UNPUBLISHED, -5, PublicationStatus.UNPUBLISHED, ''),
        (PublicationStatus.PUBLISHED, 5, PublicationStatus.PUBLISHED, ''),
        (PublicationStatus.PUBLISHED, None, PublicationStatus.PUBLISHED, ''),
        (PublicationStatus.PUBLISHED, None, PublicationStatus.PUBLISHED, 'test_redirect.com'),
    ],
)
@pytest.mark.parametrize(argnames='expose_flag', argvalues=[True, False])
def test_get_plans_by_hostname(
    graphql_client_query_data,
    plan_factory,
    plan_domain_factory,
    publication_status_override,
    delta_minutes,
    expected_publication_status,
    redirect_to,
    expose_flag,
):
    """
    Test getPlansByHostname query with excplicit PlanDomains and without authentication.

    With PlanDomains specified, the plan visibility follows the publication status of the
    plan but can be overridden via the domain.
    """
    published_at = None
    if delta_minutes is not None:
        published_at = timezone.now() + timedelta(minutes=delta_minutes)
    plan = plan_factory(published_at=published_at)
    plan.features.expose_unpublished_plan_only_to_authenticated_user = expose_flag
    plan.features.save()

    domain = plan_domain_factory(
        plan=plan, publication_status_override=publication_status_override, redirect_to_hostname=redirect_to
    )
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY,
        variables={'hostname': domain.hostname},
    )
    plans = data['plansForHostname']
    expected = [
        {
            'domains': [
                {
                    'basePath': domain.base_path,
                    'hostname': domain.hostname,
                    'status': expected_publication_status.name,
                    'redirectToHostname': domain.redirect_to_hostname or None,
                }
            ],
            'primaryLanguage': plan.primary_language,
            'publishedAt': published_at.isoformat() if published_at else None,
        },
    ]
    if expected_publication_status == PublicationStatus.PUBLISHED:
        expected[0]['identifier'] = plan.identifier
        expected[0]['id'] = plan.identifier
    assert plans == expected


@pytest.mark.parametrize(
    ('publication_status_override', 'has_message'),
    [(PublicationStatus.UNPUBLISHED, True), (PublicationStatus.PUBLISHED, False)],
)
def test_get_correct_domain_by_hostname(
    graphql_client_query_data, plan_factory, plan_domain_factory, publication_status_override, has_message
):

    plan = plan_factory()
    domain = plan_domain_factory(plan=plan, publication_status_override=publication_status_override)
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY_STATUSMESSAGE,
        variables={'hostname': domain.hostname},
    )
    plans = data['plansForHostname']
    message = plans[0]['domains'][0]['statusMessage']
    if has_message:
        assert message is not None
    else:
        assert message is None


@pytest.fixture(params=['settings', 'header', 'both'], ids=['via_settings', 'via_header', 'via_both'])
def hostname_plan_domains_with_country_wildcard(request, settings):
    """Provide wildcard pattern domain via Django settings, x-wildcard-domains request header, or both."""
    retval = {}
    settings.HOSTNAME_PLAN_DOMAINS = []
    if request.param in ('settings', 'both'):
        settings.HOSTNAME_PLAN_DOMAINS = ['watch.<country>.dummy.io']
    if request.param in ('header', 'both'):
        retval.update({'headers': {'x-wildcard-domains': 'watch.<country>.dummy.io'}})
    return retval


@pytest.fixture(params=['settings', 'header', 'both'], ids=['via_settings', 'via_header', 'via_both'])
def hostname_plan_domains_without_country_wildcard(request, settings):
    """Provide exact (non-wildcard) domain via Django settings, x-wildcard-domains request header, or both."""
    retval = {}
    settings.HOSTNAME_PLAN_DOMAINS = []
    if request.param in ('settings', 'both'):
        settings.HOSTNAME_PLAN_DOMAINS = ['dummy.io']
    if request.param in ('header', 'both'):
        retval.update({'headers': {'x-wildcard-domains': 'dummy.io'}})
    return retval


@pytest.mark.parametrize('delta_minutes', [-5, 5, None])
@pytest.mark.parametrize(argnames='expose_flag', argvalues=[True, False])
def test_plans_for_hostname_without_domains(
    graphql_client_query_data,
    hostname_plan_domains_without_country_wildcard,
    plan_factory,
    delta_minutes,
    expose_flag,
):
    published_at = None
    if delta_minutes is not None:
        published_at = timezone.now() + timedelta(minutes=delta_minutes)
    plan = plan_factory(published_at=published_at)
    plan.features.expose_unpublished_plan_only_to_authenticated_user = expose_flag
    plan.features.save()
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY,
        variables={'hostname': f'{plan.identifier}.dummy.io'},
        **hostname_plan_domains_without_country_wildcard,
    )
    planData = data['plansForHostname'][0]
    assert len(planData['domains']) == 0
    plan_is_published = delta_minutes is not None and delta_minutes < 0
    if expose_flag is False or plan_is_published:
        assert planData['identifier'] == plan.identifier
    else:
        assert 'identifier' not in planData


def test_wildcard_pattern_resolves_plan(graphql_client_query_data, hostname_plan_domains_with_country_wildcard, plan_factory):
    """Plan resolved via identifier.watch.fi.dummy.io when wildcard domain watch.<country>.dummy.io is configured."""
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.watch.fi.dummy.io'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
        **hostname_plan_domains_with_country_wildcard,
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    assert plans[0]['identifier'] == plan.identifier
    assert plans[0]['domain']['redirectToHostname'] is None


def test_wildcard_pattern_and_exact_domain_coexist(
    graphql_client_query_data, hostname_plan_domains_with_country_wildcard, settings, plan_factory
):
    """Both pattern and exact domain entries work when configured together."""
    settings.HOSTNAME_PLAN_DOMAINS = settings.HOSTNAME_PLAN_DOMAINS + ['exact.example.com']
    plan = plan_factory(country='FI')

    # Via pattern
    hostname_pattern = f'{plan.identifier}.watch.fi.dummy.io'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname_pattern},
        **hostname_plan_domains_with_country_wildcard,
    )
    assert len(data['plansForHostname']) == 1
    assert data['plansForHostname'][0]['identifier'] == plan.identifier
    assert data['plansForHostname'][0]['domain']['redirectToHostname'] is None

    # Via exact domain
    hostname_exact = f'{plan.identifier}.exact.example.com'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname_exact},
        **hostname_plan_domains_with_country_wildcard,
    )
    assert len(data['plansForHostname']) == 1
    assert data['plansForHostname'][0]['identifier'] == plan.identifier
    assert data['plansForHostname'][0]['domain']['redirectToHostname'] is None


def test_exact_domain_still_works_with_no_patterns(
    graphql_client_query_data,
    hostname_plan_domains_without_country_wildcard,
    plan_factory,
):
    """Backward compat: exact domain entries still resolve plans."""
    plan = plan_factory()
    hostname = f'{plan.identifier}.dummy.io'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
        **hostname_plan_domains_without_country_wildcard,
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    assert plans[0]['identifier'] == plan.identifier
    assert plans[0]['domain']['redirectToHostname'] is None


def test_cross_region_redirect(graphql_client_query_data, hostname_plan_domains_with_country_wildcard, plan_factory):
    """Finnish plan accessed via watch.de.dummy.io gets redirect to watch.fi.dummy.io."""
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.watch.de.dummy.io'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
        **hostname_plan_domains_with_country_wildcard,
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    domain = plans[0]['domain']
    assert domain['redirectToHostname'] == f'{plan.identifier}.watch.fi.dummy.io'


def test_correct_region_no_redirect(graphql_client_query_data, hostname_plan_domains_with_country_wildcard, plan_factory):
    """Finnish plan accessed via watch.fi.dummy.io has no redirect."""
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.watch.fi.dummy.io'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
        **hostname_plan_domains_with_country_wildcard,
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    domain = plans[0]['domain']
    assert domain['redirectToHostname'] is None


def test_non_pattern_domain_no_redirect(
    graphql_client_query_data,
    hostname_plan_domains_without_country_wildcard,
    plan_factory,
):
    """Old-style exact domain — no redirect even if plan has a different country."""
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.dummy.io'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
        **hostname_plan_domains_without_country_wildcard,
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    domain = plans[0]['domain']
    assert domain['redirectToHostname'] is None


def test_default_hostname_with_wildcard_pattern(settings, plan_factory):
    """default_hostname() generates identifier.watch.fi.dummy.io when country='FI' and pattern watch.<country>.dummy.io."""
    settings.HOSTNAME_PLAN_DOMAINS = ['watch.<country>.dummy.io']
    plan = plan_factory(country='FI')
    assert plan.default_hostname() == f'{plan.identifier}.watch.fi.dummy.io'


def test_default_hostname_with_exact_domain(settings, plan_factory):
    """default_hostname() with exact domain still works as before."""
    settings.HOSTNAME_PLAN_DOMAINS = ['dummy.io']
    plan = plan_factory()
    assert plan.default_hostname() == f'{plan.identifier}.dummy.io'


# --- Tests for legacy hostname redirect (<plan>.domain → <plan>.<country>.domain) ---


def test_legacy_hostname_resolves_and_redirects(graphql_client_query_data, settings, plan_factory):
    """Legacy <plan>.dummy.io with pattern <country>.dummy.io resolves the plan and redirects to <plan>.<country>.dummy.io."""
    settings.HOSTNAME_PLAN_DOMAINS = ['<country>.dummy.io']
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.dummy.io'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    assert plans[0]['identifier'] == plan.identifier
    assert plans[0]['domain']['redirectToHostname'] == f'{plan.identifier}.fi.dummy.io'


def test_canonical_hostname_no_redirect_simple_wildcard(graphql_client_query_data, settings, plan_factory):
    """Canonical <plan>.<country>.dummy.io with pattern <country>.dummy.io has no redirect."""
    settings.HOSTNAME_PLAN_DOMAINS = ['<country>.dummy.io']
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.fi.dummy.io'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    domain = plans[0]['domain']
    assert domain['redirectToHostname'] is None


def test_wrong_region_redirect_simple_wildcard(graphql_client_query_data, settings, plan_factory):
    """<plan>.<wrong_country>.dummy.io with pattern <country>.dummy.io redirects to correct country."""
    settings.HOSTNAME_PLAN_DOMAINS = ['<country>.dummy.io']
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.de.dummy.io'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    domain = plans[0]['domain']
    assert domain['redirectToHostname'] == f'{plan.identifier}.fi.dummy.io'


def test_legacy_hostname_resolves_and_redirects_for_mid_wildcard(graphql_client_query_data, settings, plan_factory):
    """Legacy <plan>.watch.dummy.io with pattern watch.<country>.dummy.io resolves plan, redirects to <plan>.watch.fi.dummy.io."""
    settings.HOSTNAME_PLAN_DOMAINS = ['watch.<country>.dummy.io']
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.watch.dummy.io'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    assert plans[0]['identifier'] == plan.identifier
    assert plans[0]['domain']['redirectToHostname'] == f'{plan.identifier}.watch.fi.dummy.io'
