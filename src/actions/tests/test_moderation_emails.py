"""The emails sent when an action is submitted for moderation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from wagtail.users.models import UserProfile

import pytest

from actions.models.action import ActionModeratorApprovalTask
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
    return ActionFactory.create(plan=plan, name='Action in moderation')


@pytest.fixture
def editor(action) -> User:
    return h.make_contact_person(action)


@pytest.fixture
def moderator(action) -> User:
    return h.make_moderator(action)


def emails_to(mailoutbox: list[EmailMessage], user: User) -> list[EmailMessage]:
    return [email for email in mailoutbox if user.email in email.to]


def submit(client, user: User, action: Action):
    return h.post_edit(client, user, action, 'submit', name='Draft name')


def test_moderator_email_names_the_submitter(client, mailoutbox, action, editor, moderator):
    submit(client, editor, action)

    (email,) = emails_to(mailoutbox, moderator)
    assert 'has been submitted for approval' in email.body
    assert f'Submitted by {editor}.' in email.body


def confirmations(mailoutbox: list[EmailMessage], user: User) -> list[EmailMessage]:
    return [email for email in emails_to(mailoutbox, user) if 'has been submitted for moderation' in email.subject]


def test_submitter_gets_a_confirmation(client, mailoutbox, action, editor, moderator):
    submit(client, editor, action)

    (email,) = confirmations(mailoutbox, editor)
    assert 'Your action "' in email.subject
    assert 'You will be notified when it has been reviewed.' in email.body
    assert h.edit_url(action) in email.body


def test_submitter_gets_a_confirmation_again_on_resubmitting(client, mailoutbox, action, editor, moderator):
    submit(client, editor, action)
    h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix the name'})

    h.post_edit(client, editor, action, 'restart-workflow', name='Fixed name')

    assert len(confirmations(mailoutbox, editor)) == 2


def test_approval_starting_the_next_step_sends_no_confirmation(client, mailoutbox):
    plan = PlanFactory.create()
    h.enable_moderation(plan, task_count=2)
    action = ActionFactory.create(plan=plan)
    editor = h.make_contact_person(action)
    moderator = h.make_moderator(action)
    submit(client, editor, action)

    h.post_workflow_action(client, moderator, action, 'approve')

    assert len(confirmations(mailoutbox, editor)) == 1
    assert confirmations(mailoutbox, moderator) == []


def test_submitter_without_submission_notifications_gets_no_confirmation(client, mailoutbox, action, editor, moderator):
    profile = UserProfile.get_for_user(editor)
    profile.submitted_notifications = False
    profile.save()

    submit(client, editor, action)

    assert confirmations(mailoutbox, editor) == []


def test_resubmitting_at_a_later_step_sends_a_confirmation(client, mailoutbox):
    plan = PlanFactory.create()
    h.enable_moderation(plan, task_count=2)
    action = ActionFactory.create(plan=plan)
    editor = h.make_contact_person(action)
    moderator = h.make_moderator(action)
    admin = h.make_plan_admin(plan)
    submit(client, editor, action)
    h.post_workflow_action(client, moderator, action, 'approve')
    h.post_workflow_action(client, admin, action, 'reject', {'comment': 'Please fix the name'})

    submit(client, editor, action)

    assert len(confirmations(mailoutbox, editor)) == 2


def test_submission_starting_after_a_deactivated_first_step_sends_a_confirmation(client, mailoutbox):
    plan = PlanFactory.create()
    h.enable_moderation(plan, task_count=2)
    first_task = ActionModeratorApprovalTask.objects.get(
        name='Moderation step 0', workflow_tasks__workflow=plan.features.moderation_workflow
    )
    first_task.active = False
    first_task.save(update_fields=['active'])
    action = ActionFactory.create(plan=plan)
    editor = h.make_contact_person(action)
    h.make_moderator(action)

    submit(client, editor, action)

    assert len(confirmations(mailoutbox, editor)) == 1
