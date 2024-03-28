from __future__ import annotations
from enum import StrEnum, auto

from graphql.error import GraphQLError, GraphQLErrorExtensions


class GraphQLErrorWithCode(GraphQLError):
    def __init__(
            self,
            *args,
            code: ErrorCode | None = None,
            extensions: GraphQLErrorExtensions = {},
            **kwargs
    ):
        if code:
            extensions['code'] = code
        return super().__init__(*args, extensions=extensions, **kwargs)


class ErrorCode(StrEnum):
    ACCESS_DENIED = auto()

    def create_error(self, *args, **kwargs):
        return GraphQLErrorWithCode(*args, code=self, **kwargs)
