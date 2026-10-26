from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from wagtail.admin.panels import Panel

from kausal_common.users import user_or_bust

from actions.models import Plan

if TYPE_CHECKING:
    from django.http import HttpRequest


def child_plans_in_order(parent: Plan) -> list[Plan]:
    return list(Plan.objects.qs.filter(parent=parent).in_hierarchy_order())


class ChildPlanOrderPanel(Panel):
    """Drag-and-drop ordering of a plan's child plans; each move is saved right away."""

    class BoundPanel(Panel.BoundPanel[Any, Any, Any]):
        template_name = 'actions/child_plan_order_panel.html'

        def is_shown(self) -> bool:
            plan = self.instance
            return plan.pk is not None and plan.children.exists() and super().is_shown()

        def get_context_data(self, parent_context=None):
            ctx = super().get_context_data(parent_context) or {}
            plan = self.instance
            ctx['child_plans'] = child_plans_in_order(plan)
            ctx['reorder_url'] = reverse('actions_plan_reorder_child', args=(plan.pk, 999999))
            ctx['success_message'] = _("'%(plan)s' has been moved successfully.") % {'plan': '__LABEL__'}
            return ctx


@require_POST
def reorder_child_plan_view(request: HttpRequest, parent_pk: int, child_pk: int) -> JsonResponse:
    parent = get_object_or_404(Plan, pk=parent_pk)
    if not user_or_bust(request.user).is_general_admin_for_plan(parent):
        raise PermissionDenied
    children = child_plans_in_order(parent)
    child = next((c for c in children if c.pk == child_pk), None)
    if child is None:
        return JsonResponse({'success': False}, status=404)
    try:
        position = int(request.GET.get('position', ''))
    except ValueError:
        position = len(children) - 1
    position = max(0, min(position, len(children) - 1))

    children.remove(child)
    children.insert(position, child)
    for index, plan in enumerate(children):
        plan.order = index
    with transaction.atomic():
        Plan.objects.bulk_update(children, ['order'])
        # Each child plan's site lists its siblings, so their cached responses are stale too
        for plan in children:
            transaction.on_commit(plan.invalidate_cache)
    return JsonResponse({'success': True})
