import logging

import sentry_sdk
from django.conf import settings
from graphene_django.views import GraphQLView
from graphql.error import GraphQLError

SUPPORTED_LANGUAGES = {x[0] for x in settings.LANGUAGES}
logger = logging.getLogger(__name__)


class LocaleMiddleware:
    def process_locale_directive(self, info, directive):
        for arg in directive.arguments:
            if arg.name.value == 'lang':
                lang = arg.value.value
                if lang not in SUPPORTED_LANGUAGES:
                    raise GraphQLError("unsupported language: %s" % lang, [info])
                info.context._graphql_query_language = lang

    def resolve(self, next, root, info, **kwargs):
        if root is None:
            info.context._graphql_query_language = None
            operation = info.operation
            for directive in operation.directives:
                if directive.name.value == 'locale':
                    self.process_locale_directive(info, directive)
        return next(root, info, **kwargs)


class SentryGraphQLView(GraphQLView):
    def __init__(self, *args, **kwargs):
        if 'middleware' not in kwargs:
            kwargs['middleware'] = (LocaleMiddleware,)
        super().__init__(*args, **kwargs)

    def execute_graphql_request(self, request, data, query, *args, **kwargs):
        """Extract any exceptions and send them to Sentry"""
        request._referer = self.request.META.get('HTTP_REFERER')
        logger.info('GraphQL request from %s' % request._referer)
        result = super().execute_graphql_request(request, data, query, *args, **kwargs)
        # If 'invalid' is set, it's a bad request
        if result and result.errors and not result.invalid:
            self._capture_sentry_exceptions(result.errors, query, data.get('variables'), request)
        return result

    def _capture_sentry_exceptions(self, errors, query, variables, request):
        with sentry_sdk.configure_scope() as scope:
            scope.set_extra('graphql_variables', variables)
            scope.set_extra('graphql_query', query)
            scope.set_extra('referer', request._referer)
            for error in errors:
                if hasattr(error, 'original_error'):
                    error = error.original_error
                sentry_sdk.capture_exception(error)
