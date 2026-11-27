"""Which inbox notifications an action's moderation creates."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from actions.tests import action_admin_helpers as h
from actions.tests.factories import ActionFactory, PlanFactory
from notifications.models import InboxNotification

if TYPE_CHECKING:
    from actions.models import Action, Plan
    from users.models import User

pytestmark = pytest.mark.django_db

Type = InboxNotification.Type


@pytest.fixture(autouse=True)
def moderation_ui(settings):
    settings.ENABLE_ACTION_MODERATION_UI = True


@pytest.fixture
def plan() -> Plan:
    plan = PlanFactory.create()
    h.enable_moderation(plan)
    return plan


@pytest.fixture
def action(plan) -> Action:
    return ActionFactory.create(plan=plan)


@pytest.fixture
def editor(action) -> User:
    return h.make_contact_person(action)


@pytest.fixture
def moderator(action) -> User:
    return h.make_moderator(action)


def inbox() -> list[tuple[str, InboxNotification.Type]]:
    return sorted((n.recipient.email, InboxNotification.Type(n.type)) for n in InboxNotification.objects.all())


def submit(client, user: User, action: Action):
    return h.post_edit(client, user, action, 'submit', name='Draft name')


def test_submission_notifies_the_actions_moderators(client, plan, action, editor, moderator):
    h.make_plan_admin(plan)

    submit(client, editor, action)

    assert inbox() == [(moderator.email, Type.ACTION_SUBMITTED)]
    notification = InboxNotification.objects.get()
    assert notification.content_object == action
    assert notification.plan == plan
    assert notification.actor == editor


def test_requesting_changes_notifies_the_submitter_with_the_comment(client, action, editor, moderator):
    submit(client, editor, action)
    InboxNotification.objects.all().delete()

    h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix the name'})

    assert inbox() == [(editor.email, Type.ACTION_CHANGES_REQUESTED)]
    assert InboxNotification.objects.get().comment == 'Please fix the name'


def test_approval_notifies_the_submitter(client, action, editor, moderator):
    submit(client, editor, action)
    InboxNotification.objects.all().delete()

    h.post_workflow_action(client, moderator, action, 'approve')

    assert inbox() == [(editor.email, Type.ACTION_APPROVED)]


def test_cancelling_notifies_the_actions_moderators(client, action, editor, moderator):
    submit(client, editor, action)
    InboxNotification.objects.all().delete()

    h.post_edit(client, editor, action, 'cancel-workflow')

    assert inbox() == [(moderator.email, Type.ACTION_WITHDRAWN)]


def test_actor_is_not_notified_of_their_own_submission(client, action, moderator):
    submit(client, moderator, action)

    assert inbox() == []


def test_nothing_is_created_without_the_moderation_ui(client, settings, action, editor, moderator):
    settings.ENABLE_ACTION_MODERATION_UI = False

    submit(client, editor, action)

    assert inbox() == []
