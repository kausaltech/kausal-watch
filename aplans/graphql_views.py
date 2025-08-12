from __future__ import annotations

from typing import TYPE_CHECKING, override

from django.conf import settings
from django.http import HttpRequest
from graphql.execution import ExecutionContext

from loguru import logger

from kausal_common.deployment import env_bool
from kausal_common.strawberry.views import GraphQLView, GraphQLWSConsumer, SyncGraphQLHTTPConsumer
from kausal_common.users import user_or_none

from .schema_context import WatchGraphQLContext

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.http.response import HttpResponse
    from graphql import (
        GraphQLOutputType,
    )
    from graphql.error import GraphQLError
    from strawberry.channels import (
        ChannelsRequest,
    )
    from strawberry.http.temporal_response import TemporalResponse

    from aplans.types import GQLPlanContext


SUPPORTED_LANGUAGES = {x[0] for x in settings.LANGUAGES}


logger = logger.bind(markup=True)

GRAPHQL_CAPTURE_QUERIES = env_bool('GRAPHQL_CAPTURE_QUERIES', default=False)

# FIXME: Not used anywhere; any code worth keeping?
class WatchExecutionContext(ExecutionContext):
    context_value: GQLPlanContext

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    @override
    def handle_field_error(
        self,
        error: GraphQLError,
        return_type: GraphQLOutputType,
    ) -> None:
        if settings.DEBUG and error.original_error is not None and not getattr(error, '_was_printed', False):
            exc = error.original_error
            logger.opt(exception=exc).error('GraphQL field error at {path}', path=error.path)
            setattr(error, '_was_printed', True)  # noqa: B010
        return super().handle_field_error(error, return_type)


class WatchGraphQLWSConsumer(GraphQLWSConsumer[WatchGraphQLContext]):
    @override
    async def get_context(self, request: GraphQLWSConsumer, response: GraphQLWSConsumer) -> WatchGraphQLContext:  # pyright: ignore[reportIncompatibleMethodOverride]
        base_ctx = await self.get_base_context(request, response)
        return WatchGraphQLContext(
            **base_ctx,
        )


class WatchGraphQLHTTPConsumer(SyncGraphQLHTTPConsumer[WatchGraphQLContext]):
    @override
    def get_context(self, request: ChannelsRequest, response: TemporalResponse) -> WatchGraphQLContext:
        base_ctx = self.get_base_context(request, response)
        return WatchGraphQLContext(
            **base_ctx,
        )


class WatchGraphQLView(GraphQLView[WatchGraphQLContext]):
    context_class: type[WatchGraphQLContext] = WatchGraphQLContext

    def __init__(self):
        from .schema import schema
        super().__init__(schema=schema)

    @override
    def get_context(self, request: HttpRequest, response: HttpResponse) -> WatchGraphQLContext:
        from aplans.cache import WatchObjectCache

        base_ctx = super().get_base_context(request, response)
        context = WatchGraphQLContext(
            **base_ctx,
        )
        user = user_or_none(request.user)
        context.cache = WatchObjectCache(user=user)
        return context
