import factory
from django.db.models.signals import post_save
from factory import SubFactory
from factory.django import DjangoModelFactory

from actions.tests.factories import PlanFactory
from notifications.models import NotificationType


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


@factory.django.mute_signals(post_save)
class NotificationSettingsFactory(DjangoModelFactory):
    class Meta:
        model = 'notifications.NotificationSettings'

    plan = SubFactory(PlanFactory, notification_settings=None)
    notifications_enabled = False
