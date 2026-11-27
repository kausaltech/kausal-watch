"""Who receives which email when an action goes through moderation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from actions.tests import action_admin_helpers as h
from actions.tests.factories import ActionFactory, PlanFactory

if TYPE_CHECKING:
    from django.core.mail import EmailMessage

    from actions.models import Action, Plan
    from users.models import User

pytestmark = pytest.mark.django_db


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


def recipients(mailoutbox: list[EmailMessage]) -> list[str]:
    return sorted(address for email in mailoutbox for address in email.to)


def submit(client, user: User, action: Action):
    return h.post_edit(client, user, action, 'submit', name='Draft name')


def test_submission_emails_the_actions_moderators(client, mailoutbox, plan, action, editor, moderator):
    h.make_plan_admin(plan)

    submit(client, editor, action)

    assert recipients(mailoutbox) == [moderator.email]


def test_requesting_changes_emails_the_submitter(client, mailoutbox, action, editor, moderator):
    submit(client, editor, action)
    mailoutbox.clear()

    h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix the name'})

    assert recipients(mailoutbox) == [editor.email]
    assert 'Please fix the name' in mailoutbox[0].body


def test_approval_emails_the_submitter(client, mailoutbox, action, editor, moderator):
    submit(client, editor, action)
    mailoutbox.clear()

    h.post_workflow_action(client, moderator, action, 'approve')

    assert recipients(mailoutbox) == [editor.email]


def test_cancelling_emails_the_actions_moderators(client, mailoutbox, action, editor, moderator):
    submit(client, editor, action)
    mailoutbox.clear()

    h.post_edit(client, editor, action, 'cancel-workflow')

    assert recipients(mailoutbox) == [moderator.email]
