from __future__ import annotations

from contextlib import nullcontext
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView
from wagtail.admin import messages
from wagtail.admin.views.generic.base import WagtailAdminTemplateMixin
from wagtail.models import TaskState, WorkflowState

import sentry_sdk
from loguru import logger

from kausal_common.users import user_or_bust

from actions.models.action import Action
from actions.notification_suppress import suppress_workflow_notifications

if TYPE_CHECKING:
    from django.db.models import QuerySet

    from actions.models.plan import Plan

logger = logger.bind(name='actions.bulk_approve')


@method_decorator(never_cache, name='dispatch')
class BulkApproveView(WagtailAdminTemplateMixin, TemplateView):
    template_name = 'actions/bulk_approve.html'
    header_icon = 'kausal-action'
    page_title = _('Release actions from moderation')
    model: type[Action] = Action

    def get_page_title(self):
        return self.page_title

    @cached_property
    def plan(self) -> Plan:
        return user_or_bust(self.request.user).get_active_admin_plan()

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            raise PermissionDenied
        user = user_or_bust(request.user)
        plan = self.plan
        if plan is None or plan.features.moderation_workflow is None:
            raise Http404
        if not user.is_superuser:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def _action_content_type(self) -> ContentType:
        return ContentType.objects.get_for_model(Action)

    def _workflow_states_qs(self) -> QuerySet[WorkflowState]:
        plan_action_ids = list(Action.objects.filter(plan=self.plan).values_list('pk', flat=True))
        return WorkflowState.objects.filter(
            base_content_type=self._action_content_type(),
            object_id__in=plan_action_ids,
        ).select_related('current_task_state__task', 'requested_by')

    def _split_by_status(self, states: list[WorkflowState]) -> tuple[list[WorkflowState], list[WorkflowState]]:
        in_progress = [s for s in states if s.status == WorkflowState.STATUS_IN_PROGRESS]
        needs_changes = [s for s in states if s.status == WorkflowState.STATUS_NEEDS_CHANGES]
        return in_progress, needs_changes

    def _rows(self, states: list[WorkflowState]) -> list[dict]:
        action_ids = [int(s.object_id) for s in states]
        actions_by_id = {a.pk: a for a in Action.objects.filter(pk__in=action_ids).select_related('plan')}
        rows = []
        for state in states:
            action = actions_by_id.get(int(state.object_id))
            if action is None:
                continue
            current_task = state.current_task_state.task if state.current_task_state else None
            rows.append({
                'workflow_state': state,
                'action': action,
                'current_task': current_task,
                'requested_by': state.requested_by,
                'submitted_at': state.created_at,
            })
        return rows

    def get_index_url(self) -> str:
        return reverse('actions_action_modeladmin_index')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        active = list(
            self._workflow_states_qs().filter(
                status__in=[WorkflowState.STATUS_IN_PROGRESS, WorkflowState.STATUS_NEEDS_CHANGES],
            )
        )
        in_progress, needs_changes = self._split_by_status(active)
        ctx['in_progress_rows'] = self._rows(in_progress)
        ctx['needs_changes_rows'] = self._rows(needs_changes)
        ctx['index_url'] = self.get_index_url()
        return ctx

    def post(self, request, *args, **kwargs):
        selected_pks = [pk for pk in request.POST.getlist('workflow_state_pks') if pk.isdigit()]
        send_notifications = request.POST.get('send_notifications') == 'on'

        candidates = list(
            self._workflow_states_qs().filter(
                pk__in=selected_pks,
                status=WorkflowState.STATUS_IN_PROGRESS,
            )
        )

        if not candidates:
            messages.warning(request, _('No releasable actions were selected.'))
            return redirect(request.path)

        action_ids = [int(c.object_id) for c in candidates]
        actions_by_id = {a.pk: a for a in Action.objects.filter(pk__in=action_ids).select_related('plan')}

        released: list[Action] = []
        skipped: list[Action] = []
        errors: list[tuple[Action, Exception]] = []
        released_ws_ids: list[int] = []

        suppress_cm = suppress_workflow_notifications() if not send_notifications else nullcontext()
        with suppress_cm:
            for ws in candidates:
                action = actions_by_id.get(int(ws.object_id))
                if action is None:
                    continue
                if not request.user.can_approve_action(action):
                    skipped.append(action)
                    continue
                try:
                    with transaction.atomic():
                        ws.finish(user=request.user)
                    released.append(action)
                    released_ws_ids.append(ws.pk)
                except Exception as e:
                    logger.exception(f'Bulk release failed for action {action.pk}')
                    sentry_sdk.capture_exception(e)
                    errors.append((action, e))

            if released_ws_ids:
                TaskState.objects.filter(
                    workflow_state_id__in=released_ws_ids,
                    status=TaskState.STATUS_IN_PROGRESS,
                ).update(
                    status=TaskState.STATUS_APPROVED,
                    finished_at=timezone.now(),
                    finished_by=request.user,
                )

        if released:
            messages.success(
                request,
                _('Released %(count)d actions.') % {'count': len(released)},
            )
        if skipped:
            messages.warning(
                request,
                _('%(count)d actions skipped (no permission).') % {'count': len(skipped)},
            )
        if errors:
            messages.error(
                request,
                _('%(count)d actions failed to release; see logs for details.') % {'count': len(errors)},
            )

        return redirect(self.get_index_url())
