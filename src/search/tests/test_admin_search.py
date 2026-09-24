"""
Search every admin listing and chooser through the Elasticsearch backend.

Each view's queryset filters (permission policies, plan scoping, filter sets) go through
the real query compilers, so a filter that the search index cannot serve fails here.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.urls import URLPattern, URLResolver, get_resolver

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.test import Client

pytestmark = pytest.mark.django_db

SEARCHABLE_VIEW_NAME = re.compile(r'(^|[:_])(index|index_results|results|list|choose|chooser)$')


def _iter_url_names(resolver: URLResolver, namespace: str = '', prefix: str = '') -> Iterator[tuple[str, str]]:
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLResolver):
            ns = f'{namespace}{pattern.namespace}:' if pattern.namespace else namespace
            yield from _iter_url_names(pattern, ns, prefix + str(pattern.pattern))
        elif isinstance(pattern, URLPattern) and pattern.name:
            yield f'{namespace}{pattern.name}', prefix + str(pattern.pattern)


def _searchable_admin_urls() -> list[str]:
    urls = set()
    for name, raw_route in _iter_url_names(get_resolver()):
        route = raw_route.replace('^', '').replace('$', '')
        if not route.startswith('admin/'):
            continue
        # Views that need URL arguments are out of reach of a generic sweep
        if '<' in route or '(' in route:
            continue
        if not SEARCHABLE_VIEW_NAME.search(name):
            continue
        urls.add('/' + route)
    return sorted(urls)


def _get_error(client: Client, url: str, params: dict[str, str]) -> str | None:
    try:
        response = client.get(url, params)
    except Exception as e:
        return f'{type(e).__name__}: {e}'
    if response.status_code >= 500:
        return f'HTTP {response.status_code}'
    return None


@pytest.mark.parametrize('user_kind', ['plan_admin', 'superuser'])
@pytest.mark.usefixtures('plan_with_pages')
def test_admin_search_views(client, plan_admin_user, superuser, es_requests, user_kind) -> None:
    client.force_login(plan_admin_user if user_kind == 'plan_admin' else superuser)
    failures = {}
    for url in _searchable_admin_urls():
        # A view that breaks without a search, e.g. for want of a required parameter, is
        # outside what this test is about.
        if _get_error(client, url, {}) is not None:
            continue
        error = _get_error(client, url, {'q': 'climate'})
        if error is not None:
            failures[url] = error
    assert es_requests, 'No admin view searched through Elasticsearch'
    assert not failures, '\n'.join(f'{url}: {error}' for url, error in sorted(failures.items()))
