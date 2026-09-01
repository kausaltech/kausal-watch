from __future__ import annotations

from typing import TYPE_CHECKING

from django.http import HttpRequest

if TYPE_CHECKING:
    from collections import OrderedDict
    from typing import type_check_only

    from graphql import GraphQLResolveInfo

    from kausal_common.graphene import GQLContext as CommonGQLContext, GQLInfo as CommonGQLInfo
    from kausal_common.users import UserOrAnon

    from aplans.schema_context import WatchGraphQLContext

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
    _plan_hostname: str

    if TYPE_CHECKING:

        def get_active_admin_plan(self) -> Plan: ...


def mixin_for_base[T](baseclass: type[T]) -> type[T]:
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


if TYPE_CHECKING:

    @type_check_only
    class WatchGQLContext(CommonGQLContext):  # pyright: ignore[reportGeneralTypeIssues]
        graphql_operation_name: str | None
        oauth2_error: OrderedDict[str, str]
        cache: WatchObjectCache
        _referer: str | None

    @type_check_only
    class WatchGQLInfo(CommonGQLInfo):  # pyright: ignore[reportGeneralTypeIssues]
        context: WatchGQLContext  # type: ignore[assignment]

    @type_check_only
    class GQLPlanContext(WatchGQLContext):  # pyright: ignore
        instance: Plan
        wildcard_domains: list[str]

    @type_check_only
    class GQLInstanceInfo(GraphQLResolveInfo):
        context: WatchGraphQLContext
