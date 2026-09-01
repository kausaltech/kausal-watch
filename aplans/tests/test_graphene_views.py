from __future__ import annotations

from typing import cast

from django.test import RequestFactory

from aplans.graphene_views import SentryGraphQLView
from aplans.types import WatchAPIRequest


def test_get_cache_key_returns_none_for_mutation():
    view = SentryGraphQLView.__new__(SentryGraphQLView)
    request = cast(
        'WatchAPIRequest',
        RequestFactory().post('/v1/graphql/', HTTP_X_CACHE_PLAN_IDENTIFIER='some-plan'),
    )
    assert view.get_cache_key(request, None, 'mutation { foo }', {}, None) is None
