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
    ("publication_status_override" ,"delta_minutes", "expected_publication_status", "redirect_to"),
    [(None, -5, PublicationStatus.PUBLISHED, ''),
     (None, 5, PublicationStatus.SCHEDULED, ''),
     (None, None, PublicationStatus.UNPUBLISHED, ''),
     (PublicationStatus.UNPUBLISHED, -5, PublicationStatus.UNPUBLISHED, ''),
     (PublicationStatus.PUBLISHED, 5, PublicationStatus.PUBLISHED, ''),
     (PublicationStatus.PUBLISHED, None, PublicationStatus.PUBLISHED, ''),
     (PublicationStatus.PUBLISHED, None, PublicationStatus.PUBLISHED, 'test_redirect.com')],
)
@pytest.mark.parametrize(
    argnames="expose_flag",
    argvalues=[True, False]
)
def test_get_plans_by_hostname(graphql_client_query_data,
                               plan_factory,
                               plan_domain_factory,
                               publication_status_override,
                               delta_minutes,
                               expected_publication_status,
                               redirect_to,
                               expose_flag):
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
        plan=plan,
        publication_status_override=publication_status_override,
        redirect_to_hostname=redirect_to
    )
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY,
        variables={'hostname': domain.hostname},
    )
    plans = data['plansForHostname']
    expected = [
        {
            'domains': [{
                'basePath': domain.base_path,
                'hostname': domain.hostname,
                'status': expected_publication_status.name,
                'redirectToHostname': domain.redirect_to_hostname or None,
            }],
            'primaryLanguage': plan.primary_language,
            'publishedAt': published_at.isoformat() if published_at else None,
        },
    ]
    if expected_publication_status == PublicationStatus.PUBLISHED:
        expected[0]['identifier'] = plan.identifier
        expected[0]['id'] = plan.identifier
    assert plans == expected


@pytest.mark.parametrize(
    "publication_status_override,has_message",
    [(PublicationStatus.UNPUBLISHED, True),
     (PublicationStatus.PUBLISHED, False)],
)
def test_get_correct_domain_by_hostname(graphql_client_query_data,
                                        plan_factory,
                                        plan_domain_factory,
                                        publication_status_override,
                                        has_message):

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


DUMMY_DOMAIN = 'dummy.io'
WILDCARD_PATTERN_DOMAIN = '*.dummy.io'


@pytest.fixture
def use_dummy_plan_hostname(settings):
    settings.HOSTNAME_PLAN_DOMAINS = [DUMMY_DOMAIN]


@pytest.fixture
def use_wildcard_pattern_hostname(settings):
    settings.HOSTNAME_PLAN_DOMAINS = [WILDCARD_PATTERN_DOMAIN]


@pytest.fixture(params=['settings', 'header'], ids=['via_settings', 'via_header'])
def wildcard_via(request, settings):
    """Provide wildcard pattern domain either via Django settings or via x-wildcard-domains request header."""
    if request.param == 'settings':
        settings.HOSTNAME_PLAN_DOMAINS = [WILDCARD_PATTERN_DOMAIN]
        return {}
    settings.HOSTNAME_PLAN_DOMAINS = []
    return {'headers': {'x-wildcard-domains': WILDCARD_PATTERN_DOMAIN}}


@pytest.mark.parametrize("delta_minutes", [-5, 5, None])
@pytest.mark.parametrize(argnames="expose_flag", argvalues=[True, False])
def test_plans_for_hostname_without_domains(graphql_client_query_data,
                                            use_dummy_plan_hostname,
                                            plan_factory,
                                            delta_minutes,
                                            expose_flag):
    published_at = None
    if delta_minutes is not None:
        published_at = timezone.now() + timedelta(minutes=delta_minutes)
    plan = plan_factory(published_at=published_at)
    plan.features.expose_unpublished_plan_only_to_authenticated_user = expose_flag
    plan.features.save()
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY,
        variables={'hostname': f'{plan.identifier}.{DUMMY_DOMAIN}'},
    )
    planData = data['plansForHostname'][0]
    assert len(planData['domains']) == 0
    plan_is_published = delta_minutes is not None and delta_minutes < 0
    if expose_flag is False or plan_is_published:
        assert planData['identifier'] == plan.identifier
    else:
        assert 'identifier' not in planData


def test_wildcard_pattern_resolves_plan(graphql_client_query_data,
                                        wildcard_via,
                                        plan_factory):
    """Plan resolved via identifier.fi.dummy.io when wildcard domain *.dummy.io is configured."""
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.fi.{DUMMY_DOMAIN}'
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY,
        variables={'hostname': hostname},
        **wildcard_via,
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    assert plans[0]['identifier'] == plan.identifier


def test_wildcard_pattern_and_exact_domain_coexist(graphql_client_query_data,
                                                    wildcard_via,
                                                    settings,
                                                    plan_factory):
    """Both pattern and exact domain entries work when configured together."""
    settings.HOSTNAME_PLAN_DOMAINS = settings.HOSTNAME_PLAN_DOMAINS + ['exact.example.com']
    plan = plan_factory(country='FI')

    # Via pattern
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY,
        variables={'hostname': f'{plan.identifier}.fi.{DUMMY_DOMAIN}'},
        **wildcard_via,
    )
    assert len(data['plansForHostname']) == 1
    assert data['plansForHostname'][0]['identifier'] == plan.identifier

    # Via exact domain
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY,
        variables={'hostname': f'{plan.identifier}.exact.example.com'},
        **wildcard_via,
    )
    assert len(data['plansForHostname']) == 1
    assert data['plansForHostname'][0]['identifier'] == plan.identifier


def test_exact_domain_still_works_with_no_patterns(graphql_client_query_data,
                                                    use_dummy_plan_hostname,
                                                    plan_factory):
    """Backward compat: exact domain entries still resolve plans."""
    plan = plan_factory()
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY,
        variables={'hostname': f'{plan.identifier}.{DUMMY_DOMAIN}'},
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    assert plans[0]['identifier'] == plan.identifier


def test_cross_region_redirect(graphql_client_query_data,
                                wildcard_via,
                                plan_factory):
    """Finnish plan accessed via *.de.dummy.io gets redirect to fi.dummy.io."""
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.de.{DUMMY_DOMAIN}'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
        **wildcard_via,
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    domain = plans[0]['domain']
    assert domain['redirectToHostname'] == f'{plan.identifier}.fi.{DUMMY_DOMAIN}'


def test_correct_region_no_redirect(graphql_client_query_data,
                                     wildcard_via,
                                     plan_factory):
    """Finnish plan accessed via *.fi.dummy.io has no redirect."""
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.fi.{DUMMY_DOMAIN}'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
        **wildcard_via,
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    domain = plans[0]['domain']
    assert domain['redirectToHostname'] is None


def test_non_pattern_domain_no_redirect(graphql_client_query_data,
                                         use_dummy_plan_hostname,
                                         plan_factory):
    """Old-style exact domain — no redirect even if plan has a different country."""
    plan = plan_factory(country='FI')
    hostname = f'{plan.identifier}.{DUMMY_DOMAIN}'
    data = graphql_client_query_data(
        GET_PLAN_DOMAIN_QUERY,
        variables={'hostname': hostname},
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    domain = plans[0]['domain']
    assert domain['redirectToHostname'] is None


def test_default_hostname_with_wildcard_pattern(use_wildcard_pattern_hostname,
                                                 plan_factory):
    """default_hostname() generates identifier.fi.dummy.io for plan with country='FI' and pattern *.dummy.io."""
    plan = plan_factory(country='FI')
    assert plan.default_hostname() == f'{plan.identifier}.fi.{DUMMY_DOMAIN}'


def test_default_hostname_with_exact_domain(use_dummy_plan_hostname,
                                             plan_factory):
    """default_hostname() with exact domain still works as before."""
    plan = plan_factory()
    assert plan.default_hostname() == f'{plan.identifier}.{DUMMY_DOMAIN}'


def test_default_hostname_pattern_no_country_raises(use_wildcard_pattern_hostname,
                                                     plan_factory):
    """default_hostname() raises if plan has no country and domain is a pattern."""
    plan = plan_factory(country='')
    with pytest.raises(Exception, match='no country set'):
        plan.default_hostname()
