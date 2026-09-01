from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from django.core import mail

import pytest

from actions.tests.factories import (
    ActionContactFactory,
    ActionFactory,
    ActionResponsiblePartyFactory,
    ActionTaskFactory,
    PlanFactory,
)
from admin_site.tests.factories import ClientPlanFactory
from feedback.tests.factories import UserFeedbackFactory
from indicators.tests.factories import IndicatorContactFactory, IndicatorFactory, IndicatorLevelFactory
from notifications.management.commands.send_plan_notifications import NotificationEngine
from notifications.models import AutomaticNotificationTemplate, NotificationType, SentNotification
from notifications.tests.factories import AutomaticNotificationTemplateFactory, ManuallyScheduledNotificationTemplateFactory
from orgs.tests.factories import OrganizationPlanAdminFactory
from people.tests.factories import PersonFactory

if TYPE_CHECKING:
    from actions.models.plan import Plan
    from people.models import Person

pytestmark = pytest.mark.django_db


def test_task_late():
    plan = PlanFactory.create()
    AutomaticNotificationTemplateFactory(base__plan=plan, type=NotificationType.TASK_LATE.identifier)
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    today = now.date()
    due_at = today - timedelta(days=1)
    task = ActionTaskFactory.create(action__plan=plan, due_at=due_at)
    ActionContactFactory.create(action=task.action)
    ClientPlanFactory.create(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.TASK_LATE.identifier, now=now)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1


def test_task_due_soon():
    plan = PlanFactory.create()
    AutomaticNotificationTemplateFactory(base__plan=plan, type=NotificationType.TASK_DUE_SOON.identifier)
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    today = now.date()
    due_at = today + timedelta(days=1)
    task = ActionTaskFactory.create(action__plan=plan, due_at=due_at)
    ActionContactFactory.create(action=task.action)
    ClientPlanFactory.create(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.TASK_DUE_SOON.identifier, now=now)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1


def test_not_enough_tasks():
    plan = PlanFactory.create()
    ClientPlanFactory.create(plan=plan)
    AutomaticNotificationTemplateFactory(
        base__plan=plan,
        type=NotificationType.NOT_ENOUGH_TASKS.identifier,
    )
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    action = ActionFactory.create(plan=plan)
    ActionContactFactory.create(action=action)
    engine = NotificationEngine(plan, only_type=NotificationType.NOT_ENOUGH_TASKS.identifier, now=now)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1
    SentNotification.objects.all().delete()
    today = now.date()
    due_at = today + timedelta(days=1)
    ActionTaskFactory(action=action, due_at=due_at)
    engine.generate_notifications()
    assert len(mail.outbox) == 1


def test_updated_indicator_values_late():
    plan = PlanFactory.create()
    AutomaticNotificationTemplateFactory(base__plan=plan, type=NotificationType.UPDATED_INDICATOR_VALUES_LATE.identifier)
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    today = now.date()
    due_at = today - timedelta(days=1)
    indicator = IndicatorFactory.create(organization=plan.organization, updated_values_due_at=due_at)
    IndicatorLevelFactory(indicator=indicator, plan=plan)
    IndicatorContactFactory(indicator=indicator)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.UPDATED_INDICATOR_VALUES_LATE.identifier, now=now)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1


def test_updated_indicator_values_due_soon():
    plan = PlanFactory.create()
    AutomaticNotificationTemplateFactory(base__plan=plan, type=NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON.identifier)
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    today = now.date()
    due_at = today + timedelta(days=1)
    indicator = IndicatorFactory.create(organization=plan.organization, updated_values_due_at=due_at)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    IndicatorContactFactory.create(indicator=indicator)
    ClientPlanFactory.create(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON.identifier, now=now)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1


@pytest.mark.parametrize('action_is_stale', [False, True])
def test_action_not_updated(action_is_stale):
    plan = PlanFactory.create()
    AutomaticNotificationTemplateFactory(base__plan=plan, type=NotificationType.ACTION_NOT_UPDATED.identifier)
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    updated_at = now - timedelta(days=plan.get_action_days_until_considered_stale())
    if not action_is_stale:
        updated_at += timedelta(days=1)
    action = ActionFactory(plan=plan, updated_at=updated_at)
    ActionContactFactory(action=action)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.ACTION_NOT_UPDATED.identifier, now=now)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    if action_is_stale:
        assert len(mail.outbox) == 1
    else:
        assert len(mail.outbox) == 0


@pytest.mark.parametrize(
    'iso_date,outbox_count',  # noqa: PT006
    [
        ('2000-01-01', 5),
        ('2000-01-03', 0),
        ('1999-12-31', 5),
    ],
)
def test_manually_scheduled_notification(
    iso_date,
    outbox_count,
    person,
    person_factory,
    plan,
    indicator_contact_factory,
    action_contact_factory,
    organization_plan_admin_factory,
    action_factory,
):
    # To be comparable to the trigger date,
    # now is already taken to be specified as 2000-01-01 in the plan timezone
    now = datetime(2000, 1, 1, 0, 0, tzinfo=UTC).replace(tzinfo=plan.tzinfo)

    trigger_date = date.fromisoformat(iso_date)
    person.general_admin_plans.add(plan)

    action_person = person_factory()
    action_contact_factory(action__plan=plan, person=action_person)

    indicator_person = person_factory()
    indicator_contact = indicator_contact_factory(person=indicator_person)
    indicator_contact.indicator.plans.set([plan])
    indicator_contact.indicator.save()

    opa = organization_plan_admin_factory(person=person_factory(), plan=plan)
    org = opa.organization
    action_factory(primary_org=org, plan=plan)

    ManuallyScheduledNotificationTemplateFactory(
        base__plan=plan,
        date=trigger_date,
        # In the comments:
        # how many emails this setting should result in (cumulative)
        send_to_plan_admins=True,  # 1
        send_to_custom_email=True,  # 2
        send_to_action_contact_persons=True,  # 3
        send_to_indicator_contact_persons=True,  # 4
        send_to_organization_admins=True,  # 5
    )
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.MANUALLY_SCHEDULED.identifier, now=now)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == outbox_count

    # The next day, no new notifications should not be sent (anymore)
    # ie. the outboux count should remain
    now = now + timedelta(days=1)
    engine = NotificationEngine(plan, only_type=NotificationType.MANUALLY_SCHEDULED.identifier, now=now)
    assert len(mail.outbox) == outbox_count
    engine.generate_notifications()
    assert len(mail.outbox) == outbox_count


def test_manually_scheduled_notification_reschedule(
    person: Person,
    plan: Plan,
):
    trigger_date = date.fromisoformat('2000-01-01')
    person.general_admin_plans.add(plan)

    manually_scheduled_notification = ManuallyScheduledNotificationTemplateFactory.create(
        base__plan=plan,
        date=trigger_date,
        send_to_plan_admins=True,
        send_to_custom_email=False,
        custom_email='',
        send_to_action_contact_persons=False,
        send_to_indicator_contact_persons=False,
        send_to_organization_admins=False,
    )
    ClientPlanFactory(plan=plan)

    # To be comparable to the trigger date, now is already taken to be in the plan timezone
    now = datetime(2000, 1, 1, 0, 0, tzinfo=UTC).replace(tzinfo=plan.tzinfo)
    engine = NotificationEngine(plan, only_type=NotificationType.MANUALLY_SCHEDULED.identifier, now=now)

    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1

    # Reschedule for the next day
    manually_scheduled_notification.date = manually_scheduled_notification.date + timedelta(days=1)
    manually_scheduled_notification.save()

    # Notification was scheduled for the next day but now is still the previous day
    engine.generate_notifications()
    assert len(mail.outbox) == 1

    now = now + timedelta(days=1)
    engine = NotificationEngine(plan, only_type=NotificationType.MANUALLY_SCHEDULED.identifier, now=now)
    engine.generate_notifications()
    assert len(mail.outbox) == 2


def test_indicator_notification_bubbles_to_org_admin():
    plan = PlanFactory.create()
    AutomaticNotificationTemplateFactory(
        base__plan=plan,
        type=NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON.identifier,
        custom_email='',
        send_to_custom_email=False,
        send_to_contact_persons=AutomaticNotificationTemplate.ContactPersonFallbackChain.CONTACT_PERSONS_THEN_ORG_ADMINS,
    )
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    due_at = now.date() + timedelta(days=1)
    indicator = IndicatorFactory.create(organization=plan.organization, updated_values_due_at=due_at)
    IndicatorLevelFactory(indicator=indicator, plan=plan)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON.identifier, now=now)
    assert len(mail.outbox) == 0
    org_admin = OrganizationPlanAdminFactory.create(plan=plan, organization=plan.organization)
    engine.generate_notifications()
    assert len(mail.outbox) == 1
    assert org_admin.person.user is not None
    assert mail.outbox[0].to[0] == org_admin.person.user.email


def test_action_notification_bubbles_to_org_admin_responsible_party():
    plan = PlanFactory.create()
    AutomaticNotificationTemplateFactory(
        base__plan=plan,
        type=NotificationType.ACTION_NOT_UPDATED.identifier,
        custom_email='',
        send_to_custom_email=False,
        send_to_contact_persons=AutomaticNotificationTemplate.ContactPersonFallbackChain.CONTACT_PERSONS_THEN_ORG_ADMINS,
    )
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    updated_at = now - timedelta(days=plan.get_action_days_until_considered_stale())
    action = ActionFactory.create(plan=plan, updated_at=updated_at)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.ACTION_NOT_UPDATED.identifier, now=now)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 0
    org_plan_admin = OrganizationPlanAdminFactory.create(plan=plan)
    ActionResponsiblePartyFactory.create(action=action, organization=org_plan_admin.organization)
    engine.generate_notifications()
    assert len(mail.outbox) == 1
    assert org_plan_admin.person.user is not None
    assert mail.outbox[0].to[0] == org_plan_admin.person.user.email


def test_action_notification_bubbles_to_org_admin_main_organization():
    plan = PlanFactory.create()
    AutomaticNotificationTemplateFactory(
        base__plan=plan,
        type=NotificationType.ACTION_NOT_UPDATED.identifier,
        custom_email='',
        send_to_custom_email=False,
        send_to_contact_persons=AutomaticNotificationTemplate.ContactPersonFallbackChain.CONTACT_PERSONS_THEN_ORG_ADMINS,
    )
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    updated_at = now - timedelta(days=plan.get_action_days_until_considered_stale())
    action = ActionFactory.create(plan=plan, updated_at=updated_at)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.ACTION_NOT_UPDATED.identifier, now=now)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 0
    org_plan_admin = OrganizationPlanAdminFactory.create(plan=plan)
    action.primary_org = org_plan_admin.organization
    action.save()
    engine.generate_notifications()
    assert len(mail.outbox) == 1
    assert org_plan_admin.person.user is not None
    assert mail.outbox[0].to[0] == org_plan_admin.person.user.email


def test_indicator_notification_bubbles_to_plan_admin():
    plan = PlanFactory.create()
    AutomaticNotificationTemplateFactory(
        base__plan=plan,
        type=NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON.identifier,
        custom_email='',
        send_to_custom_email=False,
        send_to_contact_persons=AutomaticNotificationTemplate.ContactPersonFallbackChain.CONTACT_PERSONS_THEN_ORG_ADMINS_THEN_PLAN_ADMINS,
    )
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    due_at = now.date() + timedelta(days=1)
    indicator = IndicatorFactory.create(organization=plan.organization, updated_values_due_at=due_at)
    IndicatorLevelFactory(indicator=indicator, plan=plan)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON.identifier, now=now)
    assert len(mail.outbox) == 0
    plan_admin = PersonFactory.create(general_admin_plans=[plan])
    engine.generate_notifications()
    assert len(mail.outbox) == 1
    assert plan_admin.user is not None
    assert mail.outbox[0].to[0] == plan_admin.user.email


def test_user_feedback_received(plan: Plan, plan_admin_person: Person):
    AutomaticNotificationTemplateFactory(base__plan=plan, type=NotificationType.USER_FEEDBACK_RECEIVED.identifier)
    ClientPlanFactory(plan=plan)
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    engine = NotificationEngine(plan, only_type=NotificationType.USER_FEEDBACK_RECEIVED.identifier, now=now)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 0
    UserFeedbackFactory(plan=plan)
    engine.generate_notifications()
    assert len(mail.outbox) == 1


def test_i18n(plan: Plan, plan_admin_person: Person):
    plan = PlanFactory.create(primary_language='de')
    AutomaticNotificationTemplateFactory(base__plan=plan, type=NotificationType.TASK_LATE.identifier)
    now = plan.to_local_timezone(datetime(2000, 1, 1, 0, 0, tzinfo=UTC))
    today = now.date()
    due_at = today - timedelta(days=1)
    task = ActionTaskFactory.create(action__plan=plan, due_at=due_at)
    ActionContactFactory.create(action=task.action)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.TASK_LATE.identifier, now=now)
    engine.generate_notifications()
    assert 'Hallo' in mail.outbox[0].body
