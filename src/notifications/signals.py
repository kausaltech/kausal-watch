from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from actions.models.features import PlanFeatures
from notifications.management.commands.initialize_notifications import seed_template_for_type
from notifications.models import BaseTemplate
from notifications.notifications import NotificationType

if TYPE_CHECKING:
    from typing import Any


@receiver(pre_save, sender=PlanFeatures)
def _snapshot_features(sender, instance: PlanFeatures, **kwargs: Any) -> None:
    prev = PlanFeatures.objects.filter(pk=instance.pk).first() if instance.pk else None
    setattr(instance, '_prev_features', prev)  # noqa: B010


@receiver(post_save, sender=PlanFeatures)
def _seed_on_gate_transition(sender, instance: PlanFeatures, **kwargs: Any) -> None:
    """Seed feature-gated notification templates when their gate flips from off to on."""
    prev = getattr(instance, '_prev_features', None)
    base_template = BaseTemplate.objects.filter(plan=instance.plan).first()
    if base_template is None:
        return
    for notification_type in NotificationType:
        cls = notification_type.value
        if 'is_enabled_for' not in cls.__dict__:
            continue
        was_enabled = prev is not None and cls.is_enabled_for(prev)
        is_enabled = cls.is_enabled_for(instance)
        if is_enabled and not was_enabled:
            seed_template_for_type(base_template, notification_type)
