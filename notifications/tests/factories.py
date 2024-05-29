import datetime
import factory
from django.db.models.signals import post_save
from factory import SubFactory
from factory.django import DjangoModelFactory

from actions.tests.factories import PlanFactory
from notifications.models import NotificationTemplate, NotificationType


class BaseTemplateFactory(DjangoModelFactory):
    class Meta:
        model = 'notifications.BaseTemplate'

    plan = SubFactory(PlanFactory)


class NotificationTemplateFactory(DjangoModelFactory):
    class Meta:
        model = 'notifications.NotificationTemplate'

    base = SubFactory(BaseTemplateFactory)
    subject = "Test"
    # Use the first notification type by default
    type = next(iter(NotificationType)).identifier
    custom_email = 'test@example.com'
    send_to_plan_admins = False
    send_to_custom_email = True
    send_to_contact_persons = NotificationTemplate.ContactPersonFallbackChain.DO_NOT_SEND


class ManuallyScheduledNotificationTemplateFactory(DjangoModelFactory):
    class Meta:
        model = 'notifications.ManuallyScheduledNotificationTemplate'

    base = SubFactory(BaseTemplateFactory)
    subject = "Test"
    date = datetime.date(2021, 1, 1)
    custom_email = 'test@example.com'
    send_to_plan_admins = True
    send_to_custom_email = True
    send_to_action_contact_persons = True
    send_to_indicator_contact_persons = True
    send_to_organization_admins = True


@factory.django.mute_signals(post_save)
class NotificationSettingsFactory(DjangoModelFactory):
    class Meta:
        model = 'notifications.NotificationSettings'

    plan = SubFactory(PlanFactory, notification_settings=None)
    notifications_enabled = False
