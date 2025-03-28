from __future__ import annotations

import dataclasses

import strawberry
from strawberry.types.field import StrawberryField

from kausal_common.strawberry.registry import register_strawberry_type

from users.models import User  # noqa: TCH001


@register_strawberry_type
@strawberry.type
class UserType:
    id: int
    email: str
    first_name: str
    last_name: str

    _user: strawberry.Private[User]

    def __init__(self, user: User):
        proper_fields = [
            field.name for field in dataclasses.fields(self)
            if not isinstance(field, StrawberryField) and field.name != '_user'
        ]
        for field in proper_fields:
            setattr(self, field, getattr(user, field))
        self._user = user
