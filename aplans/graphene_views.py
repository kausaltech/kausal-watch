import sentry_sdk
from graphene_django.views import GraphQLView


class SentryGraphQLView(GraphQLView):
    def execute_graphql_request(self, request, data, query, *args, **kwargs):
        """Extract any exceptions and send them to Sentry"""
        result = super().execute_graphql_request(request, data, query, *args, **kwargs)
        # If 'invalid' is set, it's a bad request
        if result and result.errors and not result.invalid:
            self._capture_sentry_exceptions(result.errors, query)
        return result

    def _capture_sentry_exceptions(self, errors, query):
        with sentry_sdk.configure_scope() as scope:
            scope.set_extra('graphql_query', query)
            for error in errors:
                if hasattr(error, 'original_error'):
                    error = error.original_error
                sentry_sdk.capture_exception(error)
