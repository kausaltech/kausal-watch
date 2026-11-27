"""
The notification preference switches in the account settings, as they behave today.

They are stored per plan admin and per action contact, but the notification engine does not consult them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from django.core import mail

import pytest

from actions.models import GeneralPlanAdmin
from actions.tests.factories import ActionContactFactory, ActionFactory, PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from feedback.tests.factories import UserFeedbackFactory
from notifications.engine import NotificationEngine
from notifications.models import (
    ActionContactPersonNotificationPreferences,
    AutomaticNotificationTemplate,
    GeneralPlanAdminNotificationPreferences,
)
from notifications.notifications import NotificationType
from notifications.tests.factories import AutomaticNotificationTemplateFactory

if TYPE_CHECKING:
    from actions.models import Plan
    from people.models import Person

pytestmark = pytest.mark.django_db


def send_feedback_notifications(plan: Plan, **feedback) -> list[str]:
    ClientPlanFactory.create(plan=plan)
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    engine = NotificationEngine(plan, only_type=NotificationType.USER_FEEDBACK_RECEIVED.identifier, now=now)
    UserFeedbackFactory.create(plan=plan, **feedback)
    engine.generate_notifications()
    return [address for email in mail.outbox for address in email.to]


def test_plan_admin_switch_does_not_stop_feedback_emails(plan: Plan, plan_admin_person: Person):
    AutomaticNotificationTemplateFactory.create(
        base__plan=plan,
        type=NotificationType.USER_FEEDBACK_RECEIVED.identifier,
        send_to_plan_admins=True,
        send_to_custom_email=False,
        custom_email='',
    )
    general_plan_admin = GeneralPlanAdmin.objects.get(plan=plan, person=plan_admin_person)
    preferences, _ = GeneralPlanAdminNotificationPreferences.objects.get_or_create(general_plan_admin=general_plan_admin)
    preferences.receive_feedback_notifications = False
    preferences.save()

    assert plan_admin_person.email in send_feedback_notifications(plan)


@pytest.mark.parametrize('switched_off', [False, True])
def test_action_contact_switch_does_not_stop_reminders(switched_off: bool):
    plan = PlanFactory.create()
    AutomaticNotificationTemplateFactory.create(
        base__plan=plan,
        type=NotificationType.ACTION_NOT_UPDATED.identifier,
        send_to_custom_email=False,
        custom_email='',
        send_to_contact_persons=AutomaticNotificationTemplate.ContactPersonFallbackChain.CONTACT_PERSONS,
    )
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    action = ActionFactory.create(plan=plan, updated_at=now - timedelta(days=plan.get_action_days_until_considered_stale()))
    contact = ActionContactFactory.create(action=action)
    ActionContactPersonNotificationPreferences.objects.create(
        action_contact_person=contact,
        receive_general_action_notifications=not switched_off,
        receive_action_feedback_notifications=not switched_off,
    )
    ClientPlanFactory.create(plan=plan)

    NotificationEngine(plan, only_type=NotificationType.ACTION_NOT_UPDATED.identifier, now=now).generate_notifications()

    assert contact.person.email in [address for email in mail.outbox for address in email.to]
