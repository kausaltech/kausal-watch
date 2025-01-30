from __future__ import annotations

import typing
from dataclasses import dataclass

from django.db.models import Model
from django.http.request import HttpRequest

from kausal_common.context.single import SingleValueContext, SubclassableContext

from aplans.types import WatchAdminRequest


@dataclass
class HttpRequestContext(SingleValueContext):
    def get_admin_request(self) -> WatchAdminRequest:
        req = self.get()
        assert hasattr(req, 'admin_cache')
        assert not req.user.is_anonymous
        return typing.cast(WatchAdminRequest, req)

ctx_instance = SubclassableContext('instance', Model)

ctx_request = HttpRequestContext('request', HttpRequest)
