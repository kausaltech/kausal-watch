from wagtail.search.backends.elasticsearch7 import (
    Elasticsearch7SearchBackend, Elasticsearch7SearchResults,
    Elasticsearch7SearchQueryCompiler, Elasticsearch7AutocompleteQueryCompiler,
)
from indicators.models import Indicator


class WatchSearchQueryCompiler(Elasticsearch7SearchQueryCompiler):
    def _process_filter(self, field_attname, lookup, value, check_only=False):
        # Work around Wagtail problem with M2M relationships
        if self.queryset.model == Indicator and field_attname == 'plan_id':
            field_attname = 'plans'
        return super()._process_filter(field_attname, lookup, value, check_only)


class WatchAutocompleteQueryCompiler(Elasticsearch7AutocompleteQueryCompiler):
    def _process_filter(self, field_attname, lookup, value, check_only=False):
        # Work around Wagtail problem with M2M relationships
        if self.queryset.model == Indicator and field_attname == 'plan_id':
            field_attname = 'plans'
        return super()._process_filter(field_attname, lookup, value, check_only)


class WatchSearchResults(Elasticsearch7SearchResults):
    def _get_es_body(self, for_count=False):
        body = super()._get_es_body(for_count)
        print('get_es_body')

        body["highlight"] = {
            "pre_tags": ["<i>"],
            "post_tags": ["</i>"],
            "fields": {"*description": {}, "*body": {}},
            "require_field_match": False,
        }
        return body


class WatchSearchBackend(Elasticsearch7SearchBackend):
    query_compiler_class = WatchSearchQueryCompiler
    autocomplete_query_compiler_class = WatchAutocompleteQueryCompiler
    results_class = WatchSearchResults


SearchBackend = WatchSearchBackend
