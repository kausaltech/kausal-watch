"""Tests for Plan.get_view_url."""

from types import SimpleNamespace

import pytest

from actions.tests.factories import PlanDomainFactory, PlanFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def plan(settings):
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
    return PlanFactory.create(
        identifier='myplan',
        primary_language='en',
        other_languages=['fi'],
    )


@pytest.fixture(params=['settings', 'request', 'both'], ids=['via_settings', 'via_request', 'via_both'])
def wildcard_domain(request, settings):
    retval = {}
    settings.HOSTNAME_PLAN_DOMAINS = []
    if request.param in ('settings', 'both'):
        settings.HOSTNAME_PLAN_DOMAINS = ['dummy.io']
    if request.param in ('request', 'both'):
        retval.update({'request': SimpleNamespace(wildcard_domains=['dummy.io'])})
    return retval


@pytest.fixture
def no_wildcard_domains(settings):
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']


class TestGetViewUrlNoClientUrl:
    def test_returns_url_from_default_hostname(self, plan):
        assert plan.get_view_url() == 'https://myplan.example.com'

    def test_adds_locale_prefix_for_non_primary_language(self, plan):
        url = plan.get_view_url(active_locale='fi')
        assert url == 'https://myplan.example.com/fi'

    def test_no_locale_prefix_for_primary_language(self, plan):
        url = plan.get_view_url(active_locale='en')
        assert url == 'https://myplan.example.com'

    def test_no_locale_prefix_for_unknown_language(self, plan):
        url = plan.get_view_url(active_locale='sv')
        assert url == 'https://myplan.example.com'


class TestGetViewUrlWithWildcardDomain:
    """Test get_view_url when client_url matches a HOSTNAME_PLAN_DOMAINS entry (without <country> pattern)."""

    def test_returns_url_with_plan_identifier(self, plan, wildcard_domain):
        url = plan.get_view_url(client_url='https://anything.dummy.io', **wildcard_domain)
        assert url == f'https://{plan.identifier}.dummy.io'

    def test_preserves_http_scheme(self, plan, wildcard_domain):
        url = plan.get_view_url(client_url='http://anything.dummy.io', **wildcard_domain)
        assert url == f'http://{plan.identifier}.dummy.io'

    def test_preserves_custom_port(self, plan, wildcard_domain):
        url = plan.get_view_url(client_url='https://anything.dummy.io:8080', **wildcard_domain)
        assert url == f'https://{plan.identifier}.dummy.io:8080'

    def test_strips_default_https_port(self, plan, wildcard_domain):
        url = plan.get_view_url(client_url='https://anything.dummy.io:443', **wildcard_domain)
        assert url == f'https://{plan.identifier}.dummy.io'

    def test_strips_default_http_port(self, plan, wildcard_domain):
        url = plan.get_view_url(client_url='http://anything.dummy.io:80', **wildcard_domain)
        assert url == f'http://{plan.identifier}.dummy.io'

    def test_adds_locale_prefix(self, plan, wildcard_domain):
        url = plan.get_view_url(client_url='https://anything.dummy.io', active_locale='fi', **wildcard_domain)
        assert url == f'https://{plan.identifier}.dummy.io/fi'

    def test_no_locale_prefix_for_primary_language(self, plan, wildcard_domain):
        url = plan.get_view_url(client_url='https://anything.dummy.io', active_locale='en', **wildcard_domain)
        assert url == f'https://{plan.identifier}.dummy.io'


class TestGetViewUrlWithPlanDomain:
    """Test get_view_url when client_url matches a PlanDomain."""

    def test_returns_url_with_matching_domain(self, plan):
        PlanDomainFactory.create(plan=plan, hostname='climate.city.gov')
        url = plan.get_view_url(client_url='https://climate.city.gov')
        assert url == 'https://climate.city.gov'

    def test_includes_base_path(self, plan):
        PlanDomainFactory.create(plan=plan, hostname='city.gov', base_path='/climate')
        url = plan.get_view_url(client_url='https://city.gov')
        assert url == 'https://city.gov/climate'

    def test_base_path_trailing_slash_stripped(self, plan):
        PlanDomainFactory.create(plan=plan, hostname='city.gov', base_path='/climate/')
        url = plan.get_view_url(client_url='https://city.gov')
        assert url == 'https://city.gov/climate'

    def test_preserves_custom_port(self, plan):
        PlanDomainFactory.create(plan=plan, hostname='climate.city.gov')
        url = plan.get_view_url(client_url='https://climate.city.gov:8443')
        assert url == 'https://climate.city.gov:8443'

    def test_adds_locale_prefix(self, plan):
        PlanDomainFactory.create(plan=plan, hostname='climate.city.gov')
        url = plan.get_view_url(client_url='https://climate.city.gov', active_locale='fi')
        assert url == 'https://climate.city.gov/fi'

    def test_locale_prefix_before_base_path(self, plan):
        PlanDomainFactory.create(plan=plan, hostname='city.gov', base_path='/climate')
        url = plan.get_view_url(client_url='https://city.gov', active_locale='fi')
        assert url == 'https://city.gov/fi/climate'


class TestGetViewUrlFallback:
    """Test get_view_url falls back to default_hostname URL when client_url doesn't match anything."""

    def test_falls_back_when_hostname_not_in_wildcard_or_domains(self, plan, no_wildcard_domains):
        url = plan.get_view_url(client_url='https://unknown.example.org')
        assert url == 'https://myplan.example.com'

    def test_falls_back_with_locale_prefix(self, plan, no_wildcard_domains):
        url = plan.get_view_url(client_url='https://unknown.example.org', active_locale='fi')
        assert url == 'https://myplan.example.com/fi'


@pytest.fixture
def plan_with_country(settings):
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
    return PlanFactory.create(
        identifier='myplan',
        primary_language='en',
        other_languages=['fi'],
        country='FI',
    )


@pytest.fixture(params=['settings', 'request', 'both'], ids=['via_settings', 'via_request', 'via_both'])
def mid_wildcard_domain(request, settings):
    """Provide watch.<country>.dummy.io pattern via settings, request, or both."""
    retval = {}
    settings.HOSTNAME_PLAN_DOMAINS = []
    if request.param in ('settings', 'both'):
        settings.HOSTNAME_PLAN_DOMAINS = ['watch.<country>.dummy.io']
    if request.param in ('request', 'both'):
        retval.update({'request': SimpleNamespace(wildcard_domains=['watch.<country>.dummy.io'])})
    return retval


@pytest.fixture(params=['settings', 'request', 'both'], ids=['via_settings', 'via_request', 'via_both'])
def simple_wildcard_domain(request, settings):
    """Provide <country>.dummy.io pattern via settings, request, or both."""
    retval = {}
    settings.HOSTNAME_PLAN_DOMAINS = []
    if request.param in ('settings', 'both'):
        settings.HOSTNAME_PLAN_DOMAINS = ['<country>.dummy.io']
    if request.param in ('request', 'both'):
        retval.update({'request': SimpleNamespace(wildcard_domains=['<country>.dummy.io'])})
    return retval


class TestGetViewUrlWithMidWildcardDomain:
    """Test get_view_url when client_url matches a watch.<country>.dummy.io pattern."""

    def test_returns_url_with_plan_identifier(self, plan_with_country, mid_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.watch.fi.dummy.io', **mid_wildcard_domain)
        assert url == f'https://{plan.identifier}.watch.fi.dummy.io'

    def test_preserves_http_scheme(self, plan_with_country, mid_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='http://anything.watch.fi.dummy.io', **mid_wildcard_domain)
        assert url == f'http://{plan.identifier}.watch.fi.dummy.io'

    def test_preserves_custom_port(self, plan_with_country, mid_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.watch.fi.dummy.io:8080', **mid_wildcard_domain)
        assert url == f'https://{plan.identifier}.watch.fi.dummy.io:8080'

    def test_strips_default_https_port(self, plan_with_country, mid_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.watch.fi.dummy.io:443', **mid_wildcard_domain)
        assert url == f'https://{plan.identifier}.watch.fi.dummy.io'

    def test_strips_default_http_port(self, plan_with_country, mid_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='http://anything.watch.fi.dummy.io:80', **mid_wildcard_domain)
        assert url == f'http://{plan.identifier}.watch.fi.dummy.io'

    def test_adds_locale_prefix(self, plan_with_country, mid_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.watch.fi.dummy.io', active_locale='fi', **mid_wildcard_domain)
        assert url == f'https://{plan.identifier}.watch.fi.dummy.io/fi'

    def test_no_locale_prefix_for_primary_language(self, plan_with_country, mid_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.watch.fi.dummy.io', active_locale='en', **mid_wildcard_domain)
        assert url == f'https://{plan.identifier}.watch.fi.dummy.io'

    def test_preserves_country_from_client_url(self, plan_with_country, mid_wildcard_domain):
        """The country code in the URL comes from the client_url, not the plan."""
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.watch.de.dummy.io', **mid_wildcard_domain)
        assert url == f'https://{plan.identifier}.watch.de.dummy.io'


class TestGetViewUrlWithSimpleWildcardDomain:
    """Test get_view_url when client_url matches a <country>.dummy.io pattern."""

    def test_returns_url_with_plan_identifier(self, plan_with_country, simple_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.fi.dummy.io', **simple_wildcard_domain)
        assert url == f'https://{plan.identifier}.fi.dummy.io'

    def test_preserves_http_scheme(self, plan_with_country, simple_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='http://anything.fi.dummy.io', **simple_wildcard_domain)
        assert url == f'http://{plan.identifier}.fi.dummy.io'

    def test_preserves_custom_port(self, plan_with_country, simple_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.fi.dummy.io:8080', **simple_wildcard_domain)
        assert url == f'https://{plan.identifier}.fi.dummy.io:8080'

    def test_strips_default_https_port(self, plan_with_country, simple_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.fi.dummy.io:443', **simple_wildcard_domain)
        assert url == f'https://{plan.identifier}.fi.dummy.io'

    def test_strips_default_http_port(self, plan_with_country, simple_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='http://anything.fi.dummy.io:80', **simple_wildcard_domain)
        assert url == f'http://{plan.identifier}.fi.dummy.io'

    def test_adds_locale_prefix(self, plan_with_country, simple_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.fi.dummy.io', active_locale='fi', **simple_wildcard_domain)
        assert url == f'https://{plan.identifier}.fi.dummy.io/fi'

    def test_no_locale_prefix_for_primary_language(self, plan_with_country, simple_wildcard_domain):
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.fi.dummy.io', active_locale='en', **simple_wildcard_domain)
        assert url == f'https://{plan.identifier}.fi.dummy.io'

    def test_preserves_country_from_client_url(self, plan_with_country, simple_wildcard_domain):
        """The country code in the URL comes from the client_url, not the plan."""
        plan = plan_with_country
        url = plan.get_view_url(client_url='https://anything.de.dummy.io', **simple_wildcard_domain)
        assert url == f'https://{plan.identifier}.de.dummy.io'


class TestGetViewUrlLocalhostFallback:
    """Test get_view_url falls back to localhost domain when it's the only one configured."""

    def test_falls_back_to_localhost_in_development(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['localhost']
        settings.DEPLOYMENT_TYPE = 'development'
        plan = PlanFactory.create(identifier='myplan', primary_language='en', other_languages=['fi'])
        url = plan.get_view_url()
        assert url == 'http://myplan.localhost'

    def test_falls_back_to_localhost_with_locale_prefix_in_development(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['localhost']
        settings.DEPLOYMENT_TYPE = 'development'
        plan = PlanFactory.create(identifier='myplan', primary_language='en', other_languages=['fi'])
        url = plan.get_view_url(active_locale='fi')
        assert url == 'http://myplan.localhost/fi'

    @pytest.mark.parametrize('deployment_type', ['production', 'staging', 'testing', 'wip', 'ci'])
    def test_raises_when_only_localhost_in_non_development(self, settings, deployment_type):
        settings.HOSTNAME_PLAN_DOMAINS = ['localhost']
        settings.DEPLOYMENT_TYPE = deployment_type
        plan = PlanFactory.create(identifier='myplan', primary_language='en', other_languages=['fi'])
        with pytest.raises(ValueError, match='no hostname plan domains configured'):
            plan.get_view_url()

    def test_prefers_non_localhost_domain(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['localhost', 'example.com']
        plan = PlanFactory.create(identifier='myplan', primary_language='en', other_languages=['fi'])
        url = plan.get_view_url()
        assert url == 'https://myplan.example.com'


@pytest.fixture
def plan_no_wildcards(settings):
    settings.HOSTNAME_PLAN_DOMAINS = []
    return PlanFactory.create(
        identifier='myplan',
        primary_language='en',
        other_languages=['fi'],
    )


class TestGetViewUrlPlanDomainFallback:
    """Test get_view_url falls back to PlanDomain when no client_url or no match."""

    def test_uses_plan_domain_with_base_path_when_no_client_url(self, plan_no_wildcards):
        plan = plan_no_wildcards
        PlanDomainFactory.create(plan=plan, hostname='city.gov', base_path='/climate')
        url = plan.get_view_url()
        assert url == 'https://city.gov/climate'

    def test_uses_plan_domain_without_base_path_when_no_client_url(self, plan_no_wildcards):
        plan = plan_no_wildcards
        PlanDomainFactory.create(plan=plan, hostname='climate.city.gov')
        url = plan.get_view_url()
        assert url == 'https://climate.city.gov'

    def test_skips_redirect_domains(self, plan_no_wildcards):
        plan = plan_no_wildcards
        PlanDomainFactory.create(plan=plan, hostname='old.city.gov', redirect_to_hostname='new.city.gov')
        PlanDomainFactory.create(plan=plan, hostname='new.city.gov')
        url = plan.get_view_url()
        assert url == 'https://new.city.gov'

    def test_base_path_with_locale_prefix(self, plan_no_wildcards):
        plan = plan_no_wildcards
        PlanDomainFactory.create(plan=plan, hostname='city.gov', base_path='/climate')
        url = plan.get_view_url(active_locale='fi')
        assert url == 'https://city.gov/fi/climate'

    def test_prefers_production_domain(self, plan_no_wildcards):
        plan = plan_no_wildcards
        from actions.models.plan import PlanDomain

        PlanDomainFactory.create(
            plan=plan,
            hostname='preview.city.gov',
            deployment_environment=PlanDomain.DeploymentEnvironment.PREVIEW,
        )
        PlanDomainFactory.create(
            plan=plan,
            hostname='city.gov',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )
        url = plan.get_view_url()
        assert url == 'https://city.gov'

    def test_raises_when_only_redirect_domains_and_no_wildcards(self, plan_no_wildcards):
        plan = plan_no_wildcards
        PlanDomainFactory.create(plan=plan, hostname='old.city.gov', redirect_to_hostname='new.city.gov')
        with pytest.raises(ValueError, match='no hostname plan domains configured'):
            plan.get_view_url()

    def test_uses_plan_domain_when_client_url_does_not_match(self, plan_no_wildcards):
        plan = plan_no_wildcards
        PlanDomainFactory.create(plan=plan, hostname='city.gov', base_path='/climate')
        url = plan.get_view_url(client_url='https://unknown.example.org')
        assert url == 'https://city.gov/climate'


class TestGetViewUrlPlanDomainPriority:
    """Test that a production PlanDomain takes priority over wildcard settings, but a wildcard from the UI overrides it."""

    @pytest.fixture
    def published_plan_with_production_domain(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
        plan = PlanFactory.create(
            identifier='myplan',
            primary_language='en',
            other_languages=['fi'],
        )
        from actions.models.plan import PlanDomain

        PlanDomainFactory.create(
            plan=plan,
            hostname='city.gov',
            base_path='/climate',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )
        return plan

    def test_uses_plan_domain_over_wildcard_settings_when_no_client_url(self, published_plan_with_production_domain):
        url = published_plan_with_production_domain.get_view_url()
        assert url == 'https://city.gov/climate'

    def test_uses_plan_domain_over_wildcard_settings_with_locale(self, published_plan_with_production_domain):
        url = published_plan_with_production_domain.get_view_url(active_locale='fi')
        assert url == 'https://city.gov/fi/climate'

    def test_wildcard_from_ui_overrides_plan_domain(self, published_plan_with_production_domain):
        url = published_plan_with_production_domain.get_view_url(client_url='https://anything.example.com')
        assert url == 'https://myplan.example.com'

    def test_wildcard_from_ui_overrides_plan_domain_with_locale(self, published_plan_with_production_domain):
        url = published_plan_with_production_domain.get_view_url(
            client_url='https://anything.example.com',
            active_locale='fi',
        )
        assert url == 'https://myplan.example.com/fi'

    def test_wildcard_from_request_header_overrides_plan_domain(self, published_plan_with_production_domain, settings):
        settings.HOSTNAME_PLAN_DOMAINS = []
        request = SimpleNamespace(wildcard_domains=['example.com'])
        url = published_plan_with_production_domain.get_view_url(
            client_url='https://anything.example.com',
            request=request,
        )
        assert url == 'https://myplan.example.com'

    def test_non_matching_client_url_falls_back_to_plan_domain(self, published_plan_with_production_domain):
        url = published_plan_with_production_domain.get_view_url(client_url='https://unknown.example.org')
        assert url == 'https://city.gov/climate'


class TestGetViewUrlMultipleProductionDomains:
    """When several production domains exist, selection is deterministic (first by pk) and warns."""

    @pytest.fixture
    def published_plan(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
        return PlanFactory.create(identifier='myplan', primary_language='en', other_languages=['fi'])

    def _add_production_domain(self, plan, hostname):
        from actions.models.plan import PlanDomain

        return PlanDomainFactory.create(
            plan=plan,
            hostname=hostname,
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )

    def test_picks_first_production_domain_by_pk(self, published_plan):
        self._add_production_domain(published_plan, 'first.city.gov')
        self._add_production_domain(published_plan, 'second.city.gov')
        assert published_plan.get_view_url() == 'https://first.city.gov'

    def test_warns_when_multiple_production_domains(self, published_plan, monkeypatch):
        captured = []

        def fake_capture_message(message, *args, **kwargs):
            captured.append((message, kwargs.get('level')))

        from actions.models import plan as plan_module

        monkeypatch.setattr(plan_module.sentry_sdk, 'capture_message', fake_capture_message)
        self._add_production_domain(published_plan, 'first.city.gov')
        self._add_production_domain(published_plan, 'second.city.gov')
        published_plan.get_view_url()
        assert len(captured) == 1
        message, level = captured[0]
        assert level == 'warning'
        assert '2 non-redirect production domains' in message
        assert 'first.city.gov' in message

    def test_does_not_warn_with_single_production_domain(self, published_plan, monkeypatch):
        captured = []
        from actions.models import plan as plan_module

        monkeypatch.setattr(plan_module.sentry_sdk, 'capture_message', lambda *a, **_k: captured.append(a))
        self._add_production_domain(published_plan, 'only.city.gov')
        published_plan.get_view_url()
        assert captured == []


class TestGetViewUrlUnpublishedPlan:
    """Unpublished plans should use the wildcard domain, not PRODUCTION PlanDomains."""

    @pytest.fixture
    def unpublished_plan_with_production_domain(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
        plan = PlanFactory.create(
            identifier='myplan',
            primary_language='en',
            other_languages=['fi'],
            published_at=None,
        )
        from actions.models.plan import PlanDomain

        PlanDomainFactory.create(
            plan=plan,
            hostname='city.gov',
            base_path='/climate',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )
        return plan

    def test_uses_wildcard_domain_when_no_client_url(self, unpublished_plan_with_production_domain):
        url = unpublished_plan_with_production_domain.get_view_url()
        assert url == 'https://myplan.example.com'

    def test_uses_wildcard_domain_with_locale(self, unpublished_plan_with_production_domain):
        url = unpublished_plan_with_production_domain.get_view_url(active_locale='fi')
        assert url == 'https://myplan.example.com/fi'

    def test_uses_non_production_domain_when_available(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
        from actions.models.plan import PlanDomain

        plan = PlanFactory.create(
            identifier='myplan',
            primary_language='en',
            other_languages=['fi'],
            published_at=None,
        )
        PlanDomainFactory.create(
            plan=plan,
            hostname='city.gov',
            base_path='/climate',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )
        PlanDomainFactory.create(
            plan=plan,
            hostname='preview.city.gov',
            deployment_environment=PlanDomain.DeploymentEnvironment.PREVIEW,
        )
        url = plan.get_view_url()
        assert url == 'https://preview.city.gov'

    def test_wildcard_from_ui_still_used(self, unpublished_plan_with_production_domain):
        url = unpublished_plan_with_production_domain.get_view_url(client_url='https://anything.example.com')
        assert url == 'https://myplan.example.com'

    def test_falls_back_to_wildcard_when_no_non_production_domains(self, unpublished_plan_with_production_domain):
        """Only a PRODUCTION domain exists, plan is unpublished -> use wildcard."""
        url = unpublished_plan_with_production_domain.get_view_url()
        assert url == 'https://myplan.example.com'


class TestDefaultHostnameMissingCountry:
    """A <country> wildcard domain has no resolvable hostname when the plan has no country."""

    @pytest.fixture
    def plan_no_country(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['<country>.dummy.io']
        return PlanFactory.create(
            identifier='myplan',
            primary_language='en',
            country='',
        )

    def test_default_hostname_returns_none(self, plan_no_country):
        assert plan_no_country.default_hostname() is None

    def test_default_hostname_with_all_domains_returns_none(self, plan_no_country):
        assert plan_no_country.default_hostname(include_all_domains=True) is None

    def test_get_view_url_raises(self, plan_no_country):
        with pytest.raises(ValueError, match='no hostname plan domains configured'):
            plan_no_country.get_view_url()

    def test_plan_with_country_still_resolves(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['<country>.dummy.io']
        plan = PlanFactory.create(identifier='myplan', primary_language='en', country='FI')
        assert plan.default_hostname() == 'myplan.fi.dummy.io'


class TestGetSiteNotificationContext:
    def test_view_url_uses_wildcard_when_no_plan_domain(self, plan):
        context = plan.get_site_notification_context()
        assert context['view_url'] == 'https://myplan.example.com'

    def test_view_url_uses_production_domain_for_published_plan(self, settings):
        from actions.models.plan import PlanDomain

        settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
        plan = PlanFactory.create(
            identifier='myplan',
            primary_language='en',
        )
        PlanDomainFactory.create(
            plan=plan,
            hostname='city.gov',
            base_path='/climate',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )
        context = plan.get_site_notification_context()
        assert context['view_url'] == 'https://city.gov/climate'

    def test_view_url_uses_wildcard_for_unpublished_plan_with_production_domain(self, settings):
        from actions.models.plan import PlanDomain

        settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
        plan = PlanFactory.create(
            identifier='myplan',
            primary_language='en',
            published_at=None,
        )
        PlanDomainFactory.create(
            plan=plan,
            hostname='city.gov',
            base_path='/climate',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )
        context = plan.get_site_notification_context()
        assert context['view_url'] == 'https://myplan.example.com'

    def test_view_url_uses_preview_domain_for_unpublished_plan(self, settings):
        from actions.models.plan import PlanDomain

        settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
        plan = PlanFactory.create(
            identifier='myplan',
            primary_language='en',
            published_at=None,
        )
        PlanDomainFactory.create(
            plan=plan,
            hostname='city.gov',
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION,
        )
        PlanDomainFactory.create(
            plan=plan,
            hostname='preview.city.gov',
            deployment_environment=PlanDomain.DeploymentEnvironment.PREVIEW,
        )
        context = plan.get_site_notification_context()
        assert context['view_url'] == 'https://preview.city.gov'
