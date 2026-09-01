from __future__ import annotations

from typing import TYPE_CHECKING, Any, Self

from asgiref.sync import sync_to_async

if TYPE_CHECKING:
    from strawberry import Schema
    from strawberry.types import ExecutionResult

    from kausal_common.strawberry.context import GraphQLContext


class DirectSchemaClient:
    def __init__(self, context: GraphQLContext) -> None:
        self.context = context

    def __enter__(self: Self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        pass

    @property
    def schema(self) -> Schema:
        from aplans.schema import schema

        return schema

    async def execute(
        self,
        query: str,
        operation_name: str | None = None,
        variables: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ExecutionResult:
        res = await sync_to_async(self.schema.execute_sync)(
            query, operation_name=operation_name, context_value=self.context, variable_values=variables
        )
        return res

    def get_data(self, result: ExecutionResult) -> dict[str, Any] | None:
        # FIXME: Error handling
        return result.data
