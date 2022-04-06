from __future__ import annotations
import typing

from django.http import HttpRequest
from users.models import User

if typing.TYPE_CHECKING:
    from actions.models import Plan


class WatchRequest(HttpRequest):
    pass


class AuthenticatedWatchRequest(HttpRequest):
    user: User


class WatchAdminRequest(AuthenticatedWatchRequest):
    def get_active_admin_plan(self) -> Plan:
        ...
