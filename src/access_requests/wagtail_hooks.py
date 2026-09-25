from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.paginator import Paginator
from django.urls import path
from wagtail import hooks

from kausal_common.users import user_or_bust
from kausal_common.views.types import Component

from .models import AccessRequest
from .views import approve_view, reject_view

if TYPE_CHECKING:
    from django.http import HttpRequest

    from laces.typing import RenderContext

PAGE_SIZE = 10
PAGE_PARAM = 'access_requests_page'


class AccessRequestsPanel(Component):
    name = 'access_requests'
    # Right after the site summary (100) and before the other dashboard panels.
    order = 101
    template_name = 'access_requests/panel.html'

    def get_context_data(self, parent_context: RenderContext) -> RenderContext:  # type: ignore[override]
        request: HttpRequest = parent_context['request']
        ctx: dict[str, Any] = dict(super().get_context_data(parent_context) or {})
        plan = user_or_bust(request.user).get_active_admin_plan()
        pending = AccessRequest.objects.qs.filter(plan=plan).pending().with_previous_rejection()
        paginator = Paginator(pending, PAGE_SIZE)
        ctx['page_obj'] = paginator.get_page(request.GET.get(PAGE_PARAM))
        ctx['page_param'] = PAGE_PARAM
        ctx['waiting_count'] = paginator.count
        return ctx


def _shows_panel(request: HttpRequest) -> bool:
    user = user_or_bust(request.user)
    plan = user.get_active_admin_plan(required=False)
    if plan is None:
        return False
    return plan.features.enable_access_requests and user.is_general_admin_for_plan(plan)


# Runs after the admin site's own hook, which removes every panel it does not know.
@hooks.register('construct_homepage_panels', order=500)
def add_access_requests_panel(request: HttpRequest, panels: list[Component]) -> None:
    if _shows_panel(request):
        panels.append(AccessRequestsPanel())


@hooks.register('register_admin_urls')
def register_access_request_urls():
    return [
        path('access-requests/<int:pk>/approve/', approve_view, name='access_requests_approve'),
        path('access-requests/<int:pk>/reject/', reject_view, name='access_requests_reject'),
    ]
