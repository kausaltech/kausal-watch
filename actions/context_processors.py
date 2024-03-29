from actions.models.plan import Plan
from admin_site.models import Client
from aplans.types import WatchAdminRequest


class AdminContextRequest(WatchAdminRequest):
    _active_plan: Plan | None
    _active_client: Client | None


def current_plan(request: AdminContextRequest):
    out = {}
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
            client = plan.clients.first().client
        request._active_client = client

    out['active_plan'] = plan
    out['active_client'] = client
    return out
