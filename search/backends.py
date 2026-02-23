from __future__ import annotations

import logging
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from django.utils import translation
from modeltrans.translator import get_i18n_field
from wagtail.search.backends.elasticsearch8 import (
    Elasticsearch8AutocompleteQueryCompiler,
    Elasticsearch8Index,
    Elasticsearch8SearchBackend,
    Elasticsearch8SearchQueryCompiler,
    Elasticsearch8SearchResults,
)

from modelsearch import index
from modelsearch.backends.database.postgres.postgres import PostgresSearchBackend
from modelsearch.backends.elasticsearch8 import Elasticsearch8Mapping
from modelsearch.backends.elasticsearchbase import ElasticsearchAtomicIndexRebuilder, ElasticsearchIndexRebuilder

from aplans.context_vars import ctx_request, get_admin_cache, has_admin_cache

from search.context import set_index_language

if TYPE_CHECKING:
    from django.db.models import Model

    from actions.models.plan import Plan

logger = logging.getLogger(__name__)


class WatchMapping(Elasticsearch8Mapping):
    edgengram_analyzer_config = {
        "analyzer": "edgengram_analyzer",
        "search_analyzer": "standard",
    }


class WatchSearchIndex(Elasticsearch8Index):
    def add_items[ModelT: Model](self, model: type[ModelT], items: list[ModelT]):
        return super().add_items(model, items)


class WatchSearchRebuilder(ElasticsearchIndexRebuilder):
    def start(self):
        self.lang_context = set_index_language(self.index.backend.language_code)
        self.lang_context.__enter__()
        return super().start()

    def finish(self):
        super().finish()
        self.lang_context.__exit__(None, None, None)


class WatchSearchAtomicRebuilder(ElasticsearchAtomicIndexRebuilder):
    def start(self):
        self.lang_context = set_index_language(self.index.backend.language_code)
        self.lang_context.__enter__()
        return super().start()

    def finish(self):
        super().finish()
        self.lang_context.__exit__(None, None, None)


class WatchSearchQueryCompiler(Elasticsearch8SearchQueryCompiler):
    def _process_filter(self, field_attname, lookup, value, check_only=False):
        from indicators.models import Indicator

        # Work around Wagtail problem with M2M relationships
        if self.queryset.model == Indicator and field_attname == 'plan_id':
            field_attname = 'plans'
        return super()._process_filter(field_attname, lookup, value, check_only)


class WatchAutocompleteQueryCompiler(Elasticsearch8AutocompleteQueryCompiler):
    def _process_filter(self, field_attname, lookup, value, check_only=False):
        from indicators.models import Indicator

        # Work around Wagtail problem with M2M relationships
        if self.queryset.model == Indicator and field_attname == 'plan_id':
            field_attname = 'plans'
        return super()._process_filter(field_attname, lookup, value, check_only)


class WatchSearchResults(Elasticsearch8SearchResults):
    def _backend_do_search(self, body, **kwargs):  # noqa: ANN202
        return super()._backend_do_search(body, **kwargs)

    def _get_es_body(self, for_count=False):
        body = super()._get_es_body(for_count)
        if not for_count:
            body["highlight"] = {
                "pre_tags": ["<em>"],
                "post_tags": ["</em>"],
                "fields": {"_all_text": {}},
                "require_field_match": False,
            }
        return body

    def _get_results_from_hits(self, hits):
        """Yield Django model instances from a page of hits returned by Elasticsearch."""

        # Get pks from results
        pks = [hit['fields']['pk'][0] for hit in hits]
        scores = {str(hit['fields']['pk'][0]): hit['_score'] for hit in hits}
        highlights = {str(hit['fields']['pk'][0]): hit.get('highlight', {}).get('_all_text', None) for hit in hits}

        # Initialise results dictionary
        results = {str(pk): None for pk in pks}

        # Find objects in database and add them to dict
        for obj in self.query_compiler.queryset.filter(pk__in=pks):
            results[str(obj.pk)] = obj

            if self._score_field:
                setattr(obj, self._score_field, scores.get(str(obj.pk)))
            obj._highlights = highlights.get(str(obj.pk))

        # Yield results in order given by Elasticsearch
        for pk in pks:
            result = results[str(pk)]
            if result:
                yield result


class WatchSearchBackend(Elasticsearch8SearchBackend):
    query_compiler_class = WatchSearchQueryCompiler
    index_class = WatchSearchIndex
    basic_rebuilder_class = WatchSearchRebuilder
    autocomplete_query_compiler_class = WatchAutocompleteQueryCompiler
    atomic_rebuilder_class = WatchSearchAtomicRebuilder
    results_class = WatchSearchResults
    mapping_class = WatchMapping
    settings = deepcopy(Elasticsearch8SearchBackend.settings)
    # Remove asciifolding from filters to retain umlauts and other non-ascii characters
    # FIXME: This is not working as expected.
    # settings['settings']['analysis']['analyzer']['edgengram_analyzer']['filter'] = ['edgengram']

    def __init__(self, params: dict[str, Any]):
        self.language_code = params.pop('LANGUAGE_CODE')
        super().__init__(params)

    def autocomplete(self, query, model_or_queryset, fields=None, operator=None, order_by_relevance=True):
        return super().autocomplete(query, model_or_queryset, fields, operator, order_by_relevance)


SearchBackend = WatchSearchBackend


def get_search_backend(language=None) -> WatchSearchBackend | None:
    from modelsearch.backends import (
        get_search_backend as modelsearch_get_search_backend,
    )
    from modelsearch.conf import get_app_config

    if language is None:
        language = translation.get_language()
    backend_name = 'default-%s' % language
    if backend_name not in get_app_config().get_search_backend_config():
        return None
    return modelsearch_get_search_backend(backend_name)


class ModeltransFieldProxy(index.SearchField):
    def __init__(self, field_name, original_field, **kwargs):  # pyright: ignore[reportMissingSuperCall]
        self.field_name = field_name
        self.original_field = original_field

    def value_from_object(self, obj):
        lang = translation.get_language()
        trans_field_name = f'{self.field_name}_i18n'
        for field in obj._meta.get_field('i18n').get_translated_fields():
            field_name = field.get_field_name()
            if (
                    field.original_field == self.original_field and
                    '_i18n' not in field_name and
                    getattr(obj, field_name) is not None and
                    field.get_language()[0:2].lower() == lang
            ):
                trans_field_name = field_name
        return getattr(obj, trans_field_name)

    def get_internal_type(self):
        return "CharField"

    def __getattr__(self, name: str, /):
        return getattr(self.original_field, name)


def get_modeltrans_field(search_field: index.SearchField | index.AutocompleteField, cls: Model):
    i18n_field = get_i18n_field(cls)
    original_field = super(type(search_field), search_field).get_field(cls)  # pyright: ignore[reportArgumentType]
    if i18n_field is None or search_field.field_name not in i18n_field.fields:
        return original_field
    return ModeltransFieldProxy(search_field.field_name, original_field)


class TranslatedSearchField(index.SearchField):
    def get_field(self, cls):
        return get_modeltrans_field(self, cls)


class TranslatedAutocompleteField(index.AutocompleteField):
    def get_field(self, cls):
        return get_modeltrans_field(self, cls)


class WatchDefaultSearchBackend(PostgresSearchBackend):
    """Search backend that forwards requests to the appropriate language backend."""

    def _get_admin_plan(self) -> Plan | None:
        try:
            request = ctx_request.get()
        except LookupError:
            return None
        if not has_admin_cache(request):
            return None
        admin_cache = get_admin_cache(request)
        return admin_cache.plan

    def _get_current_language_backend(self) -> WatchSearchBackend | None:
        lang = translation.get_language()
        lang = lang.split('-')[0]
        return get_search_backend(lang)

    def get_language_backend(self) -> WatchSearchBackend | None:
        admin_plan = self._get_admin_plan()
        if admin_plan is None:
            return self._get_current_language_backend()
        lang = admin_plan.primary_language.split('-')[0]
        return get_search_backend(lang)

    def autocomplete(self, query, queryset, fields=None, operator=None, order_by_relevance=True):
        lang_backend = self.get_language_backend()
        if lang_backend is None:
            return super().autocomplete(query, queryset, fields, operator, order_by_relevance)
        res = lang_backend.autocomplete(query, queryset, fields, operator, order_by_relevance)
        return res

    def search(self, query, queryset, fields=None, operator=None, order_by_relevance=True):
        lang_backend = self.get_language_backend()
        if lang_backend is None:
            return super().search(query, queryset, fields, operator, order_by_relevance)
        return lang_backend.search(query, queryset, fields, operator, order_by_relevance)
