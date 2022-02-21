import logging
from typing import Optional
from django.utils import translation
import elasticsearch_dsl as es_dsl
from wagtail.search.backends.elasticsearch7 import (
    Elasticsearch7SearchBackend, Elasticsearch7SearchResults,
    Elasticsearch7SearchQueryCompiler, Elasticsearch7AutocompleteQueryCompiler,
    Elasticsearch7Index
)
from wagtail.search.backends.elasticsearch5 import (
    ElasticsearchIndexRebuilder, ElasticsearchAtomicIndexRebuilder
)

logger = logging.getLogger(__name__)


class WatchSearchIndex(Elasticsearch7Index):
    def add_items(self, model, items):
        if not hasattr(model, 'get_primary_language'):
            logger.warn('Model %s does not define a primary language' % model)
            return
        lang = self.backend.language_code
        items = [item for item in items if item.get_primary_language() == lang]
        return super().add_items(model, items)


class WatchSearchRebuilder(ElasticsearchIndexRebuilder):
    def start(self):
        self.previous_language = translation.get_language()
        translation.activate(self.index.backend.language_code)
        return super().start()

    def finish(self):
        super().finish()
        translation.activate(self.previous_language)


class WatchSearchQueryCompiler(Elasticsearch7SearchQueryCompiler):
    def _process_filter(self, field_attname, lookup, value, check_only=False):
        from indicators.models import Indicator

        # Work around Wagtail problem with M2M relationships
        if self.queryset.model == Indicator and field_attname == 'plan_id':
            field_attname = 'plans'
        return super()._process_filter(field_attname, lookup, value, check_only)


class WatchAutocompleteQueryCompiler(Elasticsearch7AutocompleteQueryCompiler):
    def _process_filter(self, field_attname, lookup, value, check_only=False):
        from indicators.models import Indicator

        # Work around Wagtail problem with M2M relationships
        if self.queryset.model == Indicator and field_attname == 'plan_id':
            field_attname = 'plans'
        return super()._process_filter(field_attname, lookup, value, check_only)


class WatchSearchResults(Elasticsearch7SearchResults):
    def _get_es_body(self, for_count=False):
        body = super()._get_es_body(for_count)
        body["highlight"] = {
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
            "fields": {"_all_text": {}},
            "require_field_match": False,
        }
        return body

    def _get_results_from_hits(self, hits):
        """
        Yields Django model instances from a page of hits returned by Elasticsearch
        """
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
            setattr(obj, '_highlights', highlights.get(str(obj.pk)))

        # Yield results in order given by Elasticsearch
        for pk in pks:
            result = results[str(pk)]
            if result:
                yield result


class WatchSearchBackend(Elasticsearch7SearchBackend):
    query_compiler_class = WatchSearchQueryCompiler
    index_class = WatchSearchIndex
    basic_rebuilder_class = WatchSearchRebuilder
    autocomplete_query_compiler_class = WatchAutocompleteQueryCompiler
    results_class = WatchSearchResults

    def __init__(self, params: dict):
        self.language_code = params.pop('LANGUAGE_CODE')
        super().__init__(params)

    def more_like_this(self, obj):
        s = es_dsl.Search(using=self.es)
        index = self.get_index_for_model(type(obj))
        s = s.query(es_dsl.query.MoreLikeThis(fields=['_all_text'], like=[dict(_index=index.name, _id=str(obj.pk))]))
        # s = s.extra(explain=True)
        s = s.source(['pk'])
        from rich import print
        print(s.to_dict())
        resp = s.execute()
        return self._get_results_from_hits(resp.hits)
        #for h in resp[0:2]:
        #    print(h.to_dict())
        #    print(h.meta.to_dict())


SearchBackend = WatchSearchBackend


def get_search_backend(language=None) -> Optional[WatchSearchBackend]:
    from wagtail.search.backends import (
        get_search_backend as wagtail_get_search_backend,
        get_search_backend_config
    )

    if language is None:
        language = translation.get_language()
    backend_name = 'default-%s' % language
    if backend_name not in get_search_backend_config():
        return None
    return wagtail_get_search_backend(backend_name)
