from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.conf import settings
from wagtail.models import TaskState, WorkflowState
from wagtail.signals import task_cancelled, task_submitted, workflow_approved, workflow_rejected

from notifications.inbox import notify
from notifications.models import InboxNotification
from users.models import User

from .models import Action, ActionContactPerson

if TYPE_CHECKING:
    from django.db.models import QuerySet


def _action_moderators(action: Action) -> QuerySet[User]:
    moderator_ids = action.contact_persons.filter(ActionContactPerson.moderators_q()).values_list('person__user')
    return User.objects.filter(id__in=moderator_ids)


def _action_of(workflow_state: WorkflowState) -> Action | None:
    if not settings.ENABLE_ACTION_MODERATION_UI:
        return None
    obj = workflow_state.content_object
    return obj if isinstance(obj, Action) else None


def _comment(workflow_state: WorkflowState) -> str:
    task_state = workflow_state.current_task_state
    if task_state is None:
        return ''
    return task_state.specific.get_comment() or ''


def _notify_moderators(task_state: TaskState, type: InboxNotification.Type, user: User | None) -> None:
    action = _action_of(task_state.workflow_state)
    if action is None:
        return
    notify(_action_moderators(action), type, action, plan=action.plan, actor=user)


def _notify_requester(workflow_state: WorkflowState, type: InboxNotification.Type, user: User | None) -> None:
    action = _action_of(workflow_state)
    requester = cast('User | None', workflow_state.requested_by)
    if action is None or requester is None:
        return
    notify([requester], type, action, plan=action.plan, actor=user, comment=_comment(workflow_state))


def on_task_submitted(sender, instance: TaskState, user: User | None = None, **kwargs) -> None:
    _notify_moderators(instance, InboxNotification.Type.ACTION_SUBMITTED, user)


def on_task_cancelled(sender, instance: TaskState, user: User | None = None, **kwargs) -> None:
    _notify_moderators(instance, InboxNotification.Type.ACTION_WITHDRAWN, user)


def on_workflow_rejected(sender, instance: WorkflowState, user: User | None = None, **kwargs) -> None:
    _notify_requester(instance, InboxNotification.Type.ACTION_CHANGES_REQUESTED, user)


def on_workflow_approved(sender, instance: WorkflowState, user: User | None = None, **kwargs) -> None:
    _notify_requester(instance, InboxNotification.Type.ACTION_APPROVED, user)


def register_signal_handlers() -> None:
    task_submitted.connect(on_task_submitted, dispatch_uid='action_inbox_task_submitted')
    task_cancelled.connect(on_task_cancelled, dispatch_uid='action_inbox_task_cancelled')
    workflow_rejected.connect(on_workflow_rejected, sender=WorkflowState, dispatch_uid='action_inbox_workflow_rejected')
    workflow_approved.connect(on_workflow_approved, sender=WorkflowState, dispatch_uid='action_inbox_workflow_approved')
