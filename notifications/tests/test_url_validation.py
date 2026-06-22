import pytest

from notifications.utils import find_urls_in_context, is_valid_public_domain_url, validate_notification_context_urls


class TestIsValidPublicDomainUrl:
    def test_accepts_https_domain(self):
        assert is_valid_public_domain_url('https://example.com') is True

    def test_accepts_http_domain(self):
        assert is_valid_public_domain_url('http://example.com') is True

    def test_accepts_domain_with_path(self):
        assert is_valid_public_domain_url('https://plan0.example.org/actions/a1') is True

    def test_accepts_subdomain(self):
        assert is_valid_public_domain_url('https://sub.domain.example.com/path') is True

    def test_accepts_domain_with_port(self):
        assert is_valid_public_domain_url('https://example.com:8443/admin/') is True

    def test_rejects_localhost(self):
        assert is_valid_public_domain_url('http://localhost:8000/admin/') is False

    def test_rejects_localhost_no_port(self):
        assert is_valid_public_domain_url('http://localhost/something') is False

    def test_rejects_localhost_subdomain(self):
        assert is_valid_public_domain_url('https://my.localhost/thing') is False

    def test_rejects_ipv4_loopback(self):
        assert is_valid_public_domain_url('http://127.0.0.1:8000/admin/') is False

    def test_rejects_ipv4_private(self):
        assert is_valid_public_domain_url('http://192.168.1.1/admin/') is False

    def test_rejects_ipv4_public(self):
        assert is_valid_public_domain_url('http://8.8.8.8/admin/') is False

    def test_rejects_ipv6_loopback(self):
        assert is_valid_public_domain_url('http://[::1]/admin/') is False

    def test_rejects_ipv6_public(self):
        assert is_valid_public_domain_url('http://[2001:db8::1]/admin/') is False

    def test_rejects_dot_local(self):
        assert is_valid_public_domain_url('https://myhost.local/admin/') is False

    def test_rejects_dot_internal(self):
        assert is_valid_public_domain_url('https://myhost.internal/admin/') is False

    def test_rejects_dot_test(self):
        assert is_valid_public_domain_url('https://myhost.test/admin/') is False

    def test_rejects_dot_invalid(self):
        assert is_valid_public_domain_url('https://myhost.invalid/admin/') is False

    def test_rejects_empty_string(self):
        assert is_valid_public_domain_url('') is False

    def test_rejects_no_scheme(self):
        assert is_valid_public_domain_url('example.com') is False

    def test_rejects_scheme_relative_url(self):
        assert is_valid_public_domain_url('//example.com/admin/') is False

    def test_rejects_unsupported_scheme(self):
        assert is_valid_public_domain_url('ftp://example.com/admin/') is False

    def test_rejects_no_hostname(self):
        assert is_valid_public_domain_url('http:///path') is False


class TestFindUrlsInContext:
    def test_finds_url_in_flat_dict(self):
        ctx = {'admin_url': 'https://admin.example.com', 'title': 'My Plan'}
        result = find_urls_in_context(ctx)
        assert result == [('admin_url', 'https://admin.example.com')]

    def test_finds_urls_in_nested_dict(self):
        ctx = {'site': {'view_url': 'https://example.com', 'title': 'Site'}}
        result = find_urls_in_context(ctx)
        assert result == [('site.view_url', 'https://example.com')]

    def test_finds_urls_in_list_of_dicts(self):
        ctx = {'items': [{'view_url': 'https://example.com/a/1'}, {'view_url': 'https://example.com/a/2'}]}
        result = find_urls_in_context(ctx)
        assert result == [
            ('items[0].view_url', 'https://example.com/a/1'),
            ('items[1].view_url', 'https://example.com/a/2'),
        ]

    def test_ignores_non_url_strings(self):
        ctx = {'title': 'Hello world', 'count': 42, 'flag': True}
        result = find_urls_in_context(ctx)
        assert result == []

    def test_returns_empty_for_empty_context(self):
        assert find_urls_in_context({}) == []

    def test_finds_mailto(self):
        ctx = {'email_link': 'mailto:test@example.com'}
        result = find_urls_in_context(ctx)
        assert result == [('email_link', 'mailto:test@example.com')]

    def test_finds_unsupported_scheme(self):
        ctx = {'admin_url': 'ftp://example.com/admin/'}
        result = find_urls_in_context(ctx)
        assert result == [('admin_url', 'ftp://example.com/admin/')]


class TestValidateNotificationContextUrls:
    def test_passes_for_valid_urls(self):
        ctx = {
            'admin_url': 'https://admin.example.com',
            'site': {'view_url': 'https://example.com'},
        }
        validate_notification_context_urls(ctx)

    def test_raises_for_localhost_url(self):
        ctx = {'admin_url': 'http://localhost:8000'}
        with pytest.raises(ValueError, match='localhost'):
            validate_notification_context_urls(ctx)

    def test_raises_for_ip_address(self):
        ctx = {'admin_url': 'http://192.168.1.1/admin/'}
        with pytest.raises(ValueError, match=r'192\.168\.1\.1'):
            validate_notification_context_urls(ctx)

    def test_raises_for_unsupported_scheme(self):
        ctx = {'admin_url': 'ftp://example.com/admin/'}
        with pytest.raises(ValueError, match=r'ftp://example\.com'):
            validate_notification_context_urls(ctx)

    def test_raises_for_mailto(self):
        ctx = {'email_link': 'mailto:test@example.com'}
        with pytest.raises(ValueError, match=r'mailto:test@example\.com'):
            validate_notification_context_urls(ctx)

    def test_lists_all_bad_urls(self):
        ctx = {
            'admin_url': 'http://localhost:8000',
            'site': {'view_url': 'http://127.0.0.1/'},
        }
        with pytest.raises(ValueError, match=r'localhost.*127\.0\.0\.1|127\.0\.0\.1.*localhost'):
            validate_notification_context_urls(ctx)

    def test_allows_localhost_when_flag_set(self):
        ctx = {'admin_url': 'http://localhost:8000'}
        validate_notification_context_urls(ctx, allow_localhost=True)

    def test_passes_for_empty_context(self):
        validate_notification_context_urls({})
