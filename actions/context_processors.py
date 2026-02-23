from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from aplans.types import WatchAdminRequest

if TYPE_CHECKING:
    from actions.models.plan import Plan
    from admin_site.models import Client


class AdminContextRequest(WatchAdminRequest):
    _active_plan: Plan | None
    _active_client: Client | None

class ActivePlan(TypedDict):
    active_plan: Plan | None
    active_client: Client | None


def current_plan(request: AdminContextRequest):
    out: ActivePlan = ActivePlan(active_plan=None, active_client=None)
    if not request or not request.user or not request.user.is_authenticated:
        return out
    if getattr(request, '_active_plan', None):
        plan = request._active_plan
    else:
        plan = request.user.get_active_admin_plan(required=False)
        request._active_plan = plan

    if getattr(request, '_active_client', None):
        client = request._active_client
    else:
        client = None
        person = request.user.get_corresponding_person()
        if person:
            client = person.get_admin_client()
        if client is None and plan is not None:
            plan_client = plan.clients.first()
            if plan_client:
                client = plan_client.client

        request._active_client = client

    out['active_plan'] = plan
    out['active_client'] = client
    return out
