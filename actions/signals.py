from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Plan, PlanFeatures
from notifications.models import NotificationSettings


@receiver(post_save, sender=Plan)
def create_notification_settings(sender, instance, created, **kwargs):
    if created:
        NotificationSettings.objects.create(plan=instance)


@receiver(post_save, sender=Plan)
def create_plan_features(sender, instance, created, **kwargs):
    if created:
        PlanFeatures.objects.create(plan=instance)
