from __future__ import annotations

import typing
from dataclasses import dataclass

from django.db.models import Model
from django.http.request import HttpRequest

from kausal_common.context.single import SingleValueContext, SubclassableContext

if typing.TYPE_CHECKING:
    from aplans.cache import PlanSpecificCache, WatchObjectCache
    from aplans.types import WatchAdminRequest


@dataclass
class HttpRequestContext(SingleValueContext[HttpRequest]):
    def get_admin_request(self) -> WatchAdminRequest:
        req = self.get()
        assert hasattr(req, 'admin_cache')
        assert not req.user.is_anonymous
        return typing.cast('WatchAdminRequest', req)

ctx_instance = SubclassableContext('instance', Model)

ctx_request = HttpRequestContext('request', HttpRequest)


def get_admin_cache(request: HttpRequest) -> PlanSpecificCache:
    assert hasattr(request, 'admin_cache')
    return getattr(request, 'admin_cache')  # noqa: B009


def get_watch_cache() -> WatchObjectCache:
    request = ctx_request.get()
    return getattr(request, 'watch_cache')  # noqa: B009


def has_admin_cache(request: HttpRequest) -> bool:
    return hasattr(request, 'admin_cache')


def get_admin_cache_from_context() -> PlanSpecificCache | None:
    if not ctx_request.is_set():
        return None
    request = ctx_request.get()
    cache = getattr(request, 'admin_cache', None)
    return cache
