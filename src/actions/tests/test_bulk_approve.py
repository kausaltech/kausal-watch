from __future__ import annotations

from unittest.mock import patch

from django.urls import reverse
from wagtail.models import TaskState, WorkflowState
from wagtail.signals import task_submitted, workflow_approved

import pytest

from actions.tests.factories import ActionFactory, PlanFactory
from actions.tests.test_change_log_graphql import make_plan_admin

pytestmark = pytest.mark.django_db


BULK_APPROVE_URL_NAME = 'actions_action_modeladmin_bulk_approve_in_moderation'


def _submit_to_moderation(plan, action, user):
    action.save_revision(user=user)
    return plan.features.moderation_workflow.start(action, user)


@pytest.fixture
def moderation_plan(plan_with_single_task_moderation):
    plan = plan_with_single_task_moderation
    plan.features.save()
    return plan


@pytest.fixture
def multi_task_moderation_plan(plan_with_double_task_moderation):
    plan = plan_with_double_task_moderation
    plan.features.save()
    return plan


@pytest.fixture
def superuser(moderation_plan):
    user = make_plan_admin(moderation_plan)
    user.is_superuser = True
    user.save(update_fields=['is_superuser'])
    return user


@pytest.fixture
def bulk_approve_url():
    return reverse(BULK_APPROVE_URL_NAME)


def _connect_spy(signal):
    calls = []

    def spy(sender, **kwargs):
        calls.append(kwargs)

    signal.connect(spy, dispatch_uid='test-bulk-approve-spy')
    return calls, spy


def _disconnect_spy(signal, spy):
    signal.disconnect(spy, dispatch_uid='test-bulk-approve-spy')


def test_bulk_release_finishes_selected_workflows(client, moderation_plan, superuser, bulk_approve_url):
    action_a = moderation_plan.actions.first()
    action_b = ActionFactory.create(plan=moderation_plan)
    ws_a = _submit_to_moderation(moderation_plan, action_a, superuser)
    ws_b = _submit_to_moderation(moderation_plan, action_b, superuser)
    client.force_login(superuser)

    response = client.post(
        bulk_approve_url,
        data={'workflow_state_pks': [str(ws_a.pk), str(ws_b.pk)]},
    )

    assert response.status_code == 302
    ws_a.refresh_from_db()
    ws_b.refresh_from_db()
    assert ws_a.status == WorkflowState.STATUS_APPROVED
    assert ws_b.status == WorkflowState.STATUS_APPROVED
    assert not WorkflowState.objects.get_queryset().active().exists()


def test_bulk_release_only_finishes_selected(client, moderation_plan, superuser, bulk_approve_url):
    action_a = moderation_plan.actions.first()
    action_b = ActionFactory.create(plan=moderation_plan)
    ws_a = _submit_to_moderation(moderation_plan, action_a, superuser)
    ws_b = _submit_to_moderation(moderation_plan, action_b, superuser)
    client.force_login(superuser)

    client.post(
        bulk_approve_url,
        data={'workflow_state_pks': [str(ws_a.pk)]},
    )

    ws_a.refresh_from_db()
    ws_b.refresh_from_db()
    assert ws_a.status == WorkflowState.STATUS_APPROVED
    assert ws_b.status == WorkflowState.STATUS_IN_PROGRESS


def test_bulk_release_default_suppresses_all_workflow_signals(client, moderation_plan, superuser, bulk_approve_url):
    action = moderation_plan.actions.first()
    ws = _submit_to_moderation(moderation_plan, action, superuser)
    client.force_login(superuser)

    approved_calls, approved_spy = _connect_spy(workflow_approved)
    submitted_calls, submitted_spy = _connect_spy(task_submitted)
    try:
        client.post(
            bulk_approve_url,
            data={'workflow_state_pks': [str(ws.pk)]},
        )
    finally:
        _disconnect_spy(workflow_approved, approved_spy)
        _disconnect_spy(task_submitted, submitted_spy)

    assert not approved_calls
    assert not submitted_calls


def test_bulk_release_with_notifications_fires_workflow_approved(client, moderation_plan, superuser, bulk_approve_url):
    action = moderation_plan.actions.first()
    ws = _submit_to_moderation(moderation_plan, action, superuser)
    client.force_login(superuser)

    approved_calls, approved_spy = _connect_spy(workflow_approved)
    try:
        client.post(
            bulk_approve_url,
            data={
                'workflow_state_pks': [str(ws.pk)],
                'send_notifications': 'on',
            },
        )
    finally:
        _disconnect_spy(workflow_approved, approved_spy)

    assert len(approved_calls) == 1


def test_bulk_release_non_superuser_denied(client, moderation_plan, bulk_approve_url, user_factory):
    stranger = user_factory()
    client.force_login(stranger)

    response = client.post(bulk_approve_url, data={'workflow_state_pks': []})
    assert response.status_code in (302, 403, 404)


def test_bulk_release_feature_disabled_returns_404(client, bulk_approve_url):
    plain_plan = PlanFactory.create()
    admin = make_plan_admin(plain_plan)
    client.force_login(admin)

    response = client.get(bulk_approve_url)
    assert response.status_code == 404


def test_bulk_release_partial_failure_captures_others(client, moderation_plan, superuser, bulk_approve_url):
    action_a = moderation_plan.actions.first()
    action_b = ActionFactory.create(plan=moderation_plan)
    ws_a = _submit_to_moderation(moderation_plan, action_a, superuser)
    ws_b = _submit_to_moderation(moderation_plan, action_b, superuser)
    client.force_login(superuser)

    real_finish = WorkflowState.finish
    call_state = {'count': 0}

    def flaky_finish(self, user=None):
        call_state['count'] += 1
        if call_state['count'] == 1:
            raise RuntimeError('boom')
        return real_finish(self, user=user)

    with (
        patch('actions.bulk_approve.sentry_sdk.capture_exception') as capture,
        patch.object(WorkflowState, 'finish', flaky_finish),
    ):
        client.post(
            bulk_approve_url,
            data={'workflow_state_pks': [str(ws_a.pk), str(ws_b.pk)]},
        )

    ws_a.refresh_from_db()
    ws_b.refresh_from_db()
    statuses = {ws_a.status, ws_b.status}
    assert WorkflowState.STATUS_APPROVED in statuses
    assert WorkflowState.STATUS_IN_PROGRESS in statuses
    assert capture.called


def test_bulk_release_multi_task_finishes_full_workflow(client, multi_task_moderation_plan, bulk_approve_url):
    admin = make_plan_admin(multi_task_moderation_plan)
    admin.is_superuser = True
    admin.save(update_fields=['is_superuser'])
    action = multi_task_moderation_plan.actions.first()
    ws = _submit_to_moderation(multi_task_moderation_plan, action, admin)

    client.force_login(admin)
    client.post(
        bulk_approve_url,
        data={'workflow_state_pks': [str(ws.pk)]},
    )

    ws.refresh_from_db()
    assert ws.status == WorkflowState.STATUS_APPROVED
    leftover_in_progress_task_states = TaskState.objects.filter(
        workflow_state=ws,
        status=TaskState.STATUS_IN_PROGRESS,
    ).count()
    assert leftover_in_progress_task_states == 0


def test_bulk_release_ignores_workflow_states_from_other_plans(
    client,
    moderation_plan,
    superuser,
    bulk_approve_url,
    plan_with_double_task_moderation,
):
    action_other = plan_with_double_task_moderation.actions.first()
    other_admin = make_plan_admin(plan_with_double_task_moderation)
    ws_other = _submit_to_moderation(plan_with_double_task_moderation, action_other, other_admin)
    client.force_login(superuser)

    client.post(
        bulk_approve_url,
        data={'workflow_state_pks': [str(ws_other.pk)]},
    )

    ws_other.refresh_from_db()
    assert ws_other.status == WorkflowState.STATUS_IN_PROGRESS
