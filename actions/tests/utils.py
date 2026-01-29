"""Utility functions for action tests."""
from __future__ import annotations

from typing import Any

from django.contrib.contenttypes.models import ContentType

from audit_logging.models import PlanScopedModelLogEntry


def assert_log_entry_created(instance, action, user, plan):
    """Assert that a PlanScopedModelLogEntry was created for a given instance."""
    content_type = ContentType.objects.get_for_model(instance, for_concrete_model=False)
    log_entry = PlanScopedModelLogEntry.objects.filter(
        content_type=content_type,
        object_id=str(instance.pk),
        action=action,
        plan=plan
    ).first()
    assert log_entry is not None, (
        f'Expected PlanScopedModelLogEntry for {instance.__class__.__name__} '
        f'id={instance.pk}, action=\'{action}\', plan={plan.pk}, but none found'
    )
    assert log_entry.user_id == user.pk
    return log_entry


def count_log_entries(instance=None, action=None, plan=None):
    """Count PlanScopedModelLogEntry instances matching the given criteria."""
    filters: dict[str, Any] = {}
    if instance is not None:
        filters['content_type'] = ContentType.objects.get_for_model(instance, for_concrete_model=False)
        filters['object_id'] = str(instance.pk)
    if action is not None:
        filters['action'] = action
    if plan is not None:
        filters['plan'] = plan
    return PlanScopedModelLogEntry.objects.filter(**filters).count()
