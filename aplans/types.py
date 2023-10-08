from __future__ import annotations
from typing import TYPE_CHECKING, Type, TypeVar
import typing

from django.http import HttpRequest
from django.contrib.auth.models import AnonymousUser

if typing.TYPE_CHECKING:
    from actions.models import Plan
    from users.models import User


UserOrAnon: typing.TypeAlias = 'User | AnonymousUser'

class WatchRequest(HttpRequest):
    pass


class AuthenticatedWatchRequest(HttpRequest):
    user: User


class WatchAdminRequest(AuthenticatedWatchRequest):
    def get_active_admin_plan(self) -> Plan: ...  # type: ignore[empty-body]


class WatchAPIRequest(WatchRequest):
    user: UserOrAnon
    _referer: str | None


T = TypeVar('T')


def mixin_for_base(baseclass: Type[T]) -> Type[T]:
    """
    Useful function to make mixins with baseclass typehint

    ```
    class ReadonlyMixin(with_typehint(BaseAdmin))):
        ...
    ```
    """
    if TYPE_CHECKING:
        return baseclass
    return object
