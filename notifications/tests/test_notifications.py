import pytest
from datetime import date, timedelta
from django.core import mail

from actions.tests.factories import ActionContactFactory, ActionFactory, ActionTaskFactory, PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from indicators.tests.factories import IndicatorContactFactory, IndicatorFactory, IndicatorLevelFactory
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
    action = ActionFactory(plan=plan, updated_at=date(2000, 1, 1))
    ActionContactFactory(action=action)
    ClientPlanFactory(plan=plan)
    engine = NotificationEngine(plan, only_type=NotificationType.ACTION_NOT_UPDATED.identifier)
    assert len(mail.outbox) == 0
    engine.generate_notifications()
    assert len(mail.outbox) == 1
