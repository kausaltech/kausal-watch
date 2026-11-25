"""The emails sent when an action is submitted for moderation."""

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
