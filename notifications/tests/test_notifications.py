import pytest
from datetime import date, datetime, timedelta
from django.core import mail
from django.utils.timezone import make_aware

from actions.tests.factories import (
    ActionContactFactory, ActionFactory, ActionTaskFactory, PlanFactory, ActionResponsiblePartyFactory
)
from admin_site.tests.factories import ClientPlanFactory
from feedback.tests.factories import UserFeedbackFactory
from indicators.tests.factories import IndicatorContactFactory, IndicatorFactory, IndicatorLevelFactory
from orgs.tests.factories import OrganizationPlanAdminFactory
from notifications.models import NotificationType
from notifications.management.commands.send_notifications import NotificationEngine
from notifications.tests.factories import NotificationTemplateFactory

pytestmark = pytest.mark.django_db


def test_task_late():
    plan = PlanFactory()
    NotificationTemplateFactory(base__plan=plan,
                                type=NotificationType.TASK_LATE.identifier)
    due_at = date.today() - timedelta(days=1)
    task = ActionTaskFactory(action__plan=plan, due_at=due_at)
    ActionContactFactory(action=task.action)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.TASK_LATE.identifier)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1


def test_task_due_soon():
    plan = PlanFactory()
    NotificationTemplateFactory(base__plan=plan,
                                type=NotificationType.TASK_DUE_SOON.identifier)
    due_at = date.today() + timedelta(days=1)
    task = ActionTaskFactory(action__plan=plan, due_at=due_at)
    ActionContactFactory(action=task.action)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.TASK_DUE_SOON.identifier)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1


def test_updated_indicator_values_late():
    plan = PlanFactory()
    NotificationTemplateFactory(base__plan=plan,
                                type=NotificationType.UPDATED_INDICATOR_VALUES_LATE.identifier)
    due_at = date.today() - timedelta(days=1)
    indicator = IndicatorFactory(organization=plan.organization, updated_values_due_at=due_at)
    IndicatorLevelFactory(indicator=indicator, plan=plan)
    IndicatorContactFactory(indicator=indicator)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.UPDATED_INDICATOR_VALUES_LATE.identifier)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1


def test_updated_indicator_values_due_soon():
    plan = PlanFactory()
    NotificationTemplateFactory(base__plan=plan,
                                type=NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON.identifier)
    due_at = date.today() + timedelta(days=1)
    indicator = IndicatorFactory(organization=plan.organization, updated_values_due_at=due_at)
    IndicatorLevelFactory(indicator=indicator, plan=plan)
    IndicatorContactFactory(indicator=indicator)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON.identifier)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1


def test_action_not_updated():
    plan = PlanFactory()
    NotificationTemplateFactory(base__plan=plan,
                                type=NotificationType.ACTION_NOT_UPDATED.identifier)
    action = ActionFactory(plan=plan, updated_at=make_aware(datetime(2000, 1, 1, 0, 0)))
    ActionContactFactory(action=action)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.ACTION_NOT_UPDATED.identifier)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1


def test_indicator_notification_bubbles_to_org_admin():
    plan = PlanFactory()
    NotificationTemplateFactory(base__plan=plan,
                                type=NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON.identifier)
    due_at = date.today() + timedelta(days=1)
    indicator = IndicatorFactory(organization=plan.organization, updated_values_due_at=due_at)
    IndicatorLevelFactory(indicator=indicator, plan=plan)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON.identifier)
    assert len(mail.outbox) == 0
    org_admin = OrganizationPlanAdminFactory(plan=plan, organization=plan.organization)
    engine.generate_notifications()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to[0] == org_admin.person.user.email


def test_action_notification_bubbles_to_org_admin_responsible_party():
    plan = PlanFactory()
    NotificationTemplateFactory(base__plan=plan,
                                type=NotificationType.ACTION_NOT_UPDATED.identifier)
    action = ActionFactory(plan=plan, updated_at=make_aware(datetime(2000, 1, 1, 0, 0)))
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.ACTION_NOT_UPDATED.identifier)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 0
    org_plan_admin = OrganizationPlanAdminFactory(plan=plan)
    ActionResponsiblePartyFactory(action=action, organization=org_plan_admin.organization)
    engine.generate_notifications()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to[0] == org_plan_admin.person.user.email


def test_action_notification_bubbles_to_org_admin_main_organization():
    plan = PlanFactory()
    NotificationTemplateFactory(base__plan=plan,
                                type=NotificationType.ACTION_NOT_UPDATED.identifier)
    action = ActionFactory(plan=plan, updated_at=make_aware(datetime(2000, 1, 1, 0, 0)))
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.ACTION_NOT_UPDATED.identifier)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 0
    org_plan_admin = OrganizationPlanAdminFactory(plan=plan)
    action.primary_org = org_plan_admin.organization
    action.save()
    engine.generate_notifications()
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to[0] == org_plan_admin.person.user.email


def test_user_feedback_received(plan, plan_admin_person):
    NotificationTemplateFactory(base__plan=plan,
                                type=NotificationType.USER_FEEDBACK_RECEIVED.identifier)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.USER_FEEDBACK_RECEIVED.identifier)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 0
    UserFeedbackFactory(plan=plan)
    engine.generate_notifications()
    assert len(mail.outbox) == 1
