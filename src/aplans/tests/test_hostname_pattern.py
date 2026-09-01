from __future__ import annotations

from aplans.utils import get_hostname_redirect_hostname, matches_hostname_pattern


class TestMatchesHostnamePatternLegacyShortened:
    """
    Tests for the behavior where hostname has one fewer part than pattern.

    This handles the legacy case: <plan>.domain matching pattern *.domain,
    allowing redirect to <plan>.<country>.domain.
    Requires allow_shortened=True to activate.

    """

    def test_shortened_hostname_matches_simple_wildcard(self):
        """dummy.io matches *.dummy.io with no captured region."""
        is_match, region = matches_hostname_pattern('dummy.io', '*.dummy.io', allow_shortened=True)
        assert is_match is True
        assert region is None

    def test_shortened_hostname_matches_mid_wildcard(self):
        """watch.dummy.io matches watch.*.dummy.io when allow_shortened=True."""
        is_match, region = matches_hostname_pattern('watch.dummy.io', 'watch.*.dummy.io', allow_shortened=True)
        assert is_match is True
        assert region is None

    def test_shortened_hostname_does_not_match_mid_wildcard_without_flag(self):
        """watch.dummy.io does NOT match watch.*.dummy.io without allow_shortened."""
        is_match, _region = matches_hostname_pattern('watch.dummy.io', 'watch.*.dummy.io')
        assert is_match is False

    def test_shortened_hostname_non_matching_domain(self):
        """evil.io does not match *.dummy.io even though lengths align."""
        is_match, _region = matches_hostname_pattern('evil.io', '*.dummy.io', allow_shortened=True)
        assert is_match is False

    def test_shortened_hostname_single_part(self):
        """Single-part hostname 'io' does not match *.dummy.io."""
        is_match, _region = matches_hostname_pattern('io', '*.dummy.io', allow_shortened=True)
        assert is_match is False

    def test_shortened_hostname_too_short(self):
        """Hostname with two fewer parts than pattern does not match."""
        is_match, _region = matches_hostname_pattern('io', '*.example.dummy.io', allow_shortened=True)
        assert is_match is False

    def test_shortened_hostname_three_part_pattern(self):
        """example.com matches *.example.com."""
        is_match, region = matches_hostname_pattern('example.com', '*.example.com', allow_shortened=True)
        assert is_match is True
        assert region is None

    def test_normal_match_still_captures_region(self):
        """fi.dummy.io matches *.dummy.io with captured region 'fi' (existing behavior)."""
        is_match, region = matches_hostname_pattern('fi.dummy.io', '*.dummy.io')
        assert is_match is True
        assert region == 'fi'

    def test_shortened_not_enabled_by_default(self):
        """Without allow_shortened, dummy.io does NOT match *.dummy.io."""
        is_match, _region = matches_hostname_pattern('dummy.io', '*.dummy.io')
        assert is_match is False


class TestRedirectHostnameSideEffect:
    """
    Test that the shortened-hostname matching doesn't cause unintended redirects.

    get_hostname_redirect_hostname uses _matches_hostname_pattern without
    allow_shortened, so bare domains without the wildcard part should NOT match.
    """

    def test_bare_domain_does_not_match_wildcard_redirect_pattern(self):
        """watch.example.com does NOT match *.watch.example.com for redirects."""
        result = get_hostname_redirect_hostname(
            hostname='watch.example.com',
            redirect_hostnames=[('*.watch.example.com', 'watch.example.dev')],
            allowed_non_wildcard_hosts=set(),
            preserve_subdomain=True,
        )
        assert result is None

    def test_subdomain_redirect_still_works(self):
        """Normal subdomain.watch.example.com still redirects correctly."""
        result = get_hostname_redirect_hostname(
            hostname='test.watch.example.com',
            redirect_hostnames=[('*.watch.example.com', 'watch.example.dev')],
            allowed_non_wildcard_hosts=set(),
            preserve_subdomain=True,
        )
        assert result == 'test.watch.example.dev'
