from __future__ import annotations

from django.test import override_settings

import pytest

from actions.tests.factories import PlanDomainFactory, PlanFactory

pytestmark = pytest.mark.django_db


PLANS_FOR_HOSTNAME_QUERY = """
  query GetPlansByHostname($hostname: String) {
    plansForHostname(hostname: $hostname) {
      domains {
        hostname
        redirectToHostname
      }
    }
  }
"""


def _get_redirect_to_hostname(graphql_client_query_data, hostname: str) -> str | None:
    """Query redirectToHostname for a given hostname via GraphQL."""
    data = graphql_client_query_data(
        PLANS_FOR_HOSTNAME_QUERY,
        variables={'hostname': hostname},
    )
    plans = data['plansForHostname']
    assert len(plans) == 1
    domains = plans[0]['domains']
    assert len(domains) == 1
    return domains[0]['redirectToHostname']


@override_settings(REDIRECT_UI_HOSTNAMES=(('*.watch.example.com', 'watch.example.dev'),))
def test_wildcard_hostname_redirect(graphql_client_query_data):
    """Test wildcard pattern matching with subdomain preservation."""
    plan = PlanFactory.create()
    PlanDomainFactory.create(plan=plan, hostname='test.watch.example.com')

    result = _get_redirect_to_hostname(graphql_client_query_data, 'test.watch.example.com')
    assert result == 'test.watch.example.dev'


@override_settings(REDIRECT_UI_HOSTNAMES=(('*.watch.example.com', 'watch.example.dev'),))
def test_wildcard_does_not_match_multiple_levels(graphql_client_query_data):
    """Test that wildcard does not match multiple subdomain levels."""
    plan = PlanFactory.create()
    PlanDomainFactory.create(plan=plan, hostname='foo.bar.watch.example.com')

    result = _get_redirect_to_hostname(graphql_client_query_data, 'foo.bar.watch.example.com')
    assert result is None


@override_settings(REDIRECT_UI_HOSTNAMES=(('*.watch.example.com', 'watch.example.dev'),))
def test_wildcard_redirects_to_different_domain(graphql_client_query_data):
    """Test wildcard redirect to a different base domain with subdomain preservation."""
    plan = PlanFactory.create()
    PlanDomainFactory.create(plan=plan, hostname='sunnydale.watch.example.com')

    result = _get_redirect_to_hostname(graphql_client_query_data, 'sunnydale.watch.example.com')
    assert result == 'sunnydale.watch.example.dev'


@override_settings(REDIRECT_UI_HOSTNAMES=(
    ('*.watch.example.com', 'watch.example.dev'),
    ('*.old.example.com', 'new.example.com'),
))
def test_multiple_patterns_first_match_wins(graphql_client_query_data):
    """Test that first matching pattern is used."""
    plan1 = PlanFactory.create()
    PlanDomainFactory.create(plan=plan1, hostname='test.watch.example.com')

    plan2 = PlanFactory.create()
    PlanDomainFactory.create(plan=plan2, hostname='foo.old.example.com')

    result1 = _get_redirect_to_hostname(graphql_client_query_data, 'test.watch.example.com')
    assert result1 == 'test.watch.example.dev'

    result2 = _get_redirect_to_hostname(graphql_client_query_data, 'foo.old.example.com')
    assert result2 == 'foo.new.example.com'


@override_settings(REDIRECT_UI_HOSTNAMES=(('*.watch.example.com', 'watch.example.dev'),))
def test_no_match_returns_none(graphql_client_query_data):
    """Test that non-matching hostname returns None."""
    plan = PlanFactory.create()
    PlanDomainFactory.create(plan=plan, hostname='other.example.com')

    result = _get_redirect_to_hostname(graphql_client_query_data, 'other.example.com')
    assert result is None


@override_settings(REDIRECT_UI_HOSTNAMES=None)
def test_none_redirect_ui_hostnames(graphql_client_query_data):
    """Test that None REDIRECT_UI_HOSTNAMES returns None."""
    plan = PlanFactory.create()
    PlanDomainFactory.create(plan=plan, hostname='test.watch.example.com')

    result = _get_redirect_to_hostname(graphql_client_query_data, 'test.watch.example.com')
    assert result is None


@override_settings(REDIRECT_UI_HOSTNAMES=())
def test_empty_redirect_ui_hostnames(graphql_client_query_data):
    """Test that empty REDIRECT_UI_HOSTNAMES returns None."""
    plan = PlanFactory.create()
    PlanDomainFactory.create(plan=plan, hostname='test.watch.example.com')

    result = _get_redirect_to_hostname(graphql_client_query_data, 'test.watch.example.com')
    assert result is None


@override_settings(REDIRECT_UI_HOSTNAMES=(('old.example.com', 'new.example.com'),))
def test_exact_hostname_match(graphql_client_query_data):
    """Test exact hostname match without wildcards."""
    plan = PlanFactory.create()
    PlanDomainFactory.create(plan=plan, hostname='old.example.com')

    result = _get_redirect_to_hostname(graphql_client_query_data, 'old.example.com')
    assert result == 'new.example.com'


@override_settings(REDIRECT_UI_HOSTNAMES=(('old.example.com', 'new.example.com'),))
def test_exact_hostname_no_match(graphql_client_query_data):
    """Test that exact hostname pattern doesn't match different hostname."""
    plan = PlanFactory.create()
    PlanDomainFactory.create(plan=plan, hostname='other.example.com')

    result = _get_redirect_to_hostname(graphql_client_query_data, 'other.example.com')
    assert result is None


@override_settings(REDIRECT_UI_HOSTNAMES=(('*.example.com', 'example.dev'),))
def test_wildcard_matches_valid_subdomain_chars(graphql_client_query_data):
    """Test that wildcard matches alphanumeric and hyphens."""
    valid_subdomains = ['test', 'test-123', 'a', '123', 'foo-bar-baz']

    for subdomain in valid_subdomains:
        hostname = f'{subdomain}.example.com'
        plan = PlanFactory.create()
        PlanDomainFactory.create(plan=plan, hostname=hostname)

        result = _get_redirect_to_hostname(graphql_client_query_data, hostname)
        assert result == f'{subdomain}.example.dev', f'Should redirect for subdomain: {subdomain}'


@override_settings(REDIRECT_UI_HOSTNAMES=(('*.example.com', 'example.dev'),))
def test_wildcard_rejects_invalid_subdomain_chars(graphql_client_query_data):
    """Test that wildcard rejects invalid subdomain characters."""
    for hostname in ['-test.example.com', 'test-.example.com']:
        plan = PlanFactory.create()
        PlanDomainFactory.create(plan=plan, hostname=hostname)

        result = _get_redirect_to_hostname(graphql_client_query_data, hostname)
        assert result is None, f'Should not redirect for hostname: {hostname}'


@override_settings(REDIRECT_UI_HOSTNAMES=(('*.example.com', 'admin.example.com'),))
def test_wildcard_does_not_match_if_already_target(graphql_client_query_data):
    """Test that wildcard does not redirect when hostname is already the target."""
    plan = PlanFactory.create()
    PlanDomainFactory.create(plan=plan, hostname='admin.example.com')

    result = _get_redirect_to_hostname(graphql_client_query_data, 'admin.example.com')
    assert result is None


@override_settings(REDIRECT_UI_HOSTNAMES=(('*.watch.example.com', 'watch.example.dev'),))
def test_model_redirect_takes_precedence_over_setting(graphql_client_query_data):
    """Test that PlanDomain.redirect_to_hostname takes precedence over REDIRECT_UI_HOSTNAMES."""
    plan = PlanFactory.create()
    PlanDomainFactory.create(
        plan=plan,
        hostname='test.watch.example.com',
        redirect_to_hostname='custom.example.com',
    )

    result = _get_redirect_to_hostname(graphql_client_query_data, 'test.watch.example.com')
    assert result == 'custom.example.com'
