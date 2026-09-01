from __future__ import annotations

from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

import pytest

from aplans.middleware import HostnameRedirectMiddleware


def get_response_success(request):
    """Mock get_response that returns success."""
    return HttpResponse('OK')


@pytest.fixture
def request_factory():
    """Fixture providing a RequestFactory instance."""
    return RequestFactory()


@override_settings(REDIRECT_HOSTNAMES=(('*.watch.example.com', 'admin.watch.example.com'),))
def test_wildcard_hostname_redirect(request_factory):
    """Test wildcard pattern matching and redirect."""
    middleware = HostnameRedirectMiddleware(get_response_success)
    request = request_factory.get('/', HTTP_HOST='test.watch.example.com')

    response = middleware(request)

    assert response.status_code == 301
    assert response['Location'] == 'http://admin.watch.example.com/'


@override_settings(REDIRECT_HOSTNAMES=(('*.watch.example.com', 'watch.example.com'),))
def test_wildcard_does_not_match_multiple_levels(request_factory):
    """Test that wildcard does not match multiple subdomain levels."""
    middleware = HostnameRedirectMiddleware(get_response_success)
    request = request_factory.get('/', HTTP_HOST='foo.bar.watch.example.com')

    response = middleware(request)

    # Should NOT redirect - passes through
    assert response.status_code == 200
    assert response.content == b'OK'


@override_settings(REDIRECT_HOSTNAMES=(('*.watch.example.com', 'watch.example.com'),))
def test_path_preservation(request_factory):
    """Test that redirect preserves the original path and query string."""
    middleware = HostnameRedirectMiddleware(get_response_success)
    request = request_factory.get('/admin/?foo=bar', HTTP_HOST='test.watch.example.com')

    response = middleware(request)

    assert response.status_code == 301
    assert response['Location'] == 'http://watch.example.com/admin/?foo=bar'


@override_settings(REDIRECT_HOSTNAMES=(('*.watch.example.com', 'watch.example.com'),))
def test_https_scheme_preservation(request_factory):
    """Test that HTTPS scheme is preserved in redirect."""
    middleware = HostnameRedirectMiddleware(get_response_success)
    request = request_factory.get('/', HTTP_HOST='test.watch.example.com', secure=True)

    response = middleware(request)

    assert response.status_code == 301
    assert response['Location'] == 'https://watch.example.com/'


@override_settings(REDIRECT_HOSTNAMES=(('*.watch.example.com', 'watch.example.com:8080'),))
def test_port_in_target_hostname(request_factory):
    """Test redirecting to target hostname with port."""
    middleware = HostnameRedirectMiddleware(get_response_success)
    request = request_factory.get('/', HTTP_HOST='test.watch.example.com')

    response = middleware(request)

    assert response.status_code == 301
    assert response['Location'] == 'http://watch.example.com:8080/'


@override_settings(
    REDIRECT_HOSTNAMES=(
        ('*.watch.example.com', 'watch.example.com'),
        ('*.old.example.com', 'new.example.com'),
    )
)
def test_multiple_patterns_first_match_wins(request_factory):
    """Test that first matching pattern is used."""
    middleware = HostnameRedirectMiddleware(get_response_success)

    # Test first pattern
    request1 = request_factory.get('/', HTTP_HOST='test.watch.example.com')
    response1 = middleware(request1)
    assert response1['Location'] == 'http://watch.example.com/'

    # Test second pattern
    request2 = request_factory.get('/', HTTP_HOST='foo.old.example.com')
    response2 = middleware(request2)
    assert response2['Location'] == 'http://new.example.com/'


@override_settings(REDIRECT_HOSTNAMES=(('*.watch.example.com', 'watch.example.com'),))
def test_no_match_passes_through(request_factory):
    """Test that non-matching hostname returns normal response."""
    middleware = HostnameRedirectMiddleware(get_response_success)
    request = request_factory.get('/', HTTP_HOST='example.com')

    response = middleware(request)

    assert response.status_code == 200
    assert response.content == b'OK'


@override_settings(REDIRECT_HOSTNAMES=())
def test_empty_redirect_hostnames(request_factory):
    """Test that empty REDIRECT_HOSTNAMES throws."""
    with pytest.raises(MiddlewareNotUsed):
        HostnameRedirectMiddleware(get_response_success)


@override_settings(REDIRECT_HOSTNAMES=(('old.example.com', 'new.example.com'),))
def test_exact_hostname_match(request_factory):
    """Test exact hostname match without wildcards."""
    middleware = HostnameRedirectMiddleware(get_response_success)
    request = request_factory.get('/', HTTP_HOST='old.example.com')

    response = middleware(request)

    assert response.status_code == 301
    assert response['Location'] == 'http://new.example.com/'


@override_settings(REDIRECT_HOSTNAMES=(('old.example.com', 'new.example.com'),))
def test_exact_hostname_no_match(request_factory):
    """Test that exact hostname pattern doesn't match different hostname."""
    middleware = HostnameRedirectMiddleware(get_response_success)
    request = request_factory.get('/', HTTP_HOST='other.example.com')

    response = middleware(request)

    assert response.status_code == 200
    assert response.content == b'OK'


@override_settings(REDIRECT_HOSTNAMES=(('*.example.com', 'example.com'),))
def test_wildcard_matches_valid_subdomain_chars(request_factory):
    """Test that wildcard matches alphanumeric and hyphens."""
    middleware = HostnameRedirectMiddleware(get_response_success)

    # Valid subdomain parts
    valid_subdomains = ['test', 'test-123', 'a', '123', 'foo-bar-baz']
    for subdomain in valid_subdomains:
        request = request_factory.get('/', HTTP_HOST=f'{subdomain}.example.com')
        response = middleware(request)
        assert response.status_code == 301, f'Should redirect for subdomain: {subdomain}'


@override_settings(REDIRECT_HOSTNAMES=(('*.example.com', 'example.com'),))
def test_wildcard_rejects_invalid_subdomain_chars(request_factory):
    """Test that wildcard rejects invalid subdomain characters."""
    middleware = HostnameRedirectMiddleware(get_response_success)

    # Invalid subdomain parts
    request = request_factory.get('/', HTTP_HOST='-test.example.com')  # starts with hyphen
    response = middleware(request)
    assert response.status_code == 200  # Should NOT redirect

    request = request_factory.get('/', HTTP_HOST='test-.example.com')  # ends with hyphen
    response = middleware(request)
    assert response.status_code == 200  # Should NOT redirect


@override_settings(REDIRECT_HOSTNAMES=(('*.example.com', 'admin.example.com'),))
def test_wildcard_does_not_match_if_already_target(request_factory):
    """Test that wildcard does not match a nonexistent part in the domain name."""
    middleware = HostnameRedirectMiddleware(get_response_success)

    # Valid subdomain parts
    request = request_factory.get('/', HTTP_HOST='admin.example.com')
    response = middleware(request)
    assert response.status_code == 200, 'Should not redirect for admin.example.com'


@override_settings(
    ALLOWED_HOSTS=(('.example.com', 'admin.example.com', 'api.example.com')),
    REDIRECT_HOSTNAMES=(('*.example.com', 'admin.example.com'),),
)
def test_wildcard_does_not_match_if_in_allowed_hosts(request_factory):
    """Test that wildcard does not match an allowed host."""
    middleware = HostnameRedirectMiddleware(get_response_success)

    # Valid subdomain parts
    request = request_factory.get('/', HTTP_HOST='api.example.com')
    response = middleware(request)
    assert response.status_code == 200, 'Should not redirect for api.example.com'
