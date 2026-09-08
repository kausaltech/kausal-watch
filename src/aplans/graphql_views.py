from __future__ import annotations

from typing import TYPE_CHECKING, override

from kausal_common.strawberry.views import GraphQLView, GraphQLWSConsumer, SyncGraphQLHTTPConsumer
from kausal_common.users import user_or_none

from .schema_context import WatchGraphQLContext

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.http.response import HttpResponse
    from strawberry.channels import (
        ChannelsRequest,
    )
    from strawberry.http.temporal_response import TemporalResponse


class WatchGraphQLWSConsumer(GraphQLWSConsumer[WatchGraphQLContext]):
    @override
    async def get_context(self, request: GraphQLWSConsumer, response: GraphQLWSConsumer) -> WatchGraphQLContext:
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
