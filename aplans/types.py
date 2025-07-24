from __future__ import annotations

import typing
from typing import TYPE_CHECKING, TypeVar

from django.http import HttpRequest

if typing.TYPE_CHECKING:
    from kausal_common.users import UserOrAnon

    from aplans.cache import OrganizationActionCountCache

    from actions.models import Plan
    from users.models import User

    from .cache import PlanSpecificCache, WatchObjectCache


class WatchRequest(HttpRequest):
    watch_cache: WatchObjectCache


class AuthenticatedWatchRequest(WatchRequest):
    user: User


class WatchAdminRequest(AuthenticatedWatchRequest):
    admin_cache: PlanSpecificCache
    if TYPE_CHECKING:
        def get_active_admin_plan(self) -> Plan: ...


class WatchAPIRequest(WatchRequest):
    user: UserOrAnon
    _referer: str | None
    wildcard_domains: list[str] | None
    organization_action_count_cache: OrganizationActionCountCache
    _plan_hostname: str

    if TYPE_CHECKING:
        def get_active_admin_plan(self) -> Plan: ...

T = TypeVar('T')


def mixin_for_base(baseclass: type[T]) -> type[T]:
    """
    Make mixins with baseclass typehint.

    ```
    class ReadonlyMixin(with_typehint(BaseAdmin))):
        ...
    ```
    """
    if TYPE_CHECKING:
        return baseclass
    return object
