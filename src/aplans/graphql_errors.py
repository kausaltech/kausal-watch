from __future__ import annotations

from enum import StrEnum, auto

from graphql.error import GraphQLError


class GraphQLErrorWithCode(GraphQLError):  # noqa: N818
    def __init__(
        self,
        *args,
        code: ErrorCode | None = None,
        **kwargs,
    ):
        extensions = kwargs.pop('extensions') or {}
        if code:
            extensions['code'] = code
        kwargs['extensions'] = extensions
        super().__init__(*args, **kwargs)


class ErrorCode(StrEnum):
    ACCESS_DENIED = auto()

    def create_error(self, *args, **kwargs):
        return GraphQLErrorWithCode(*args, code=self, **kwargs)
