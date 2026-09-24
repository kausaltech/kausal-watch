from __future__ import annotations

from collections import defaultdict
from typing import Any

import pytest

from search.backends import WatchSearchResults


@pytest.fixture
def es_requests(settings, monkeypatch) -> list[dict[str, Any]]:
    """
    Route searches to an Elasticsearch language backend and record the bodies sent to it.

    The test settings configure no Elasticsearch, so the query compilers that turn a
    queryset's filters into an Elasticsearch body would otherwise never run. Only the HTTP
    call is stubbed out: it answers every search with no hits.
    """
    settings.WAGTAILSEARCH_BACKENDS = {
        'default': {'BACKEND': 'search.backends.WatchDefaultSearchBackend', 'AUTO_UPDATE': False},
        'default-en': {
            'BACKEND': 'search.backends',
            'URLS': ['http://elasticsearch.invalid:9200'],
            'INDEX': 'watch-en',
            'LANGUAGE_CODE': 'en',
            'AUTO_UPDATE': False,
        },
    }
    requests: list[dict[str, Any]] = []

    def fake_search(_self, body, **kwargs) -> dict[str, Any]:
        requests.append({'index': kwargs.get('index'), **body})
        # Faceted searches read the buckets of an aggregation named after the field
        return {'hits': {'hits': []}, 'aggregations': defaultdict(lambda: {'buckets': []})}

    monkeypatch.setattr(WatchSearchResults, '_backend_do_search', fake_search)
    monkeypatch.setattr(WatchSearchResults, '_do_count', lambda _self: 0)
    return requests
