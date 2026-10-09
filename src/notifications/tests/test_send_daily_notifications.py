from __future__ import annotations

from datetime import UTC, datetime, time
from unittest import mock

from django.core.management import call_command

import pytest

from actions.tests.factories import PlanFactory
from notifications.engine import NotificationEngine

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def _due_plan(identifier: str):
    return PlanFactory.create(
        identifier=identifier,
        notification_settings__notifications_enabled=True,
        notification_settings__send_at_time=time(0, 0),
    )


def test_one_failing_plan_does_not_stop_the_others(monkeypatch):
    failing = _due_plan('failing-plan')
    working = _due_plan('working-plan')
    processed: list[str] = []

    def fake_generate_notifications(engine: NotificationEngine) -> None:
        if engine.plan == failing:
            raise ValueError('Notification context contains non-public URLs')
        processed.append(engine.plan.identifier)

    monkeypatch.setattr(NotificationEngine, 'generate_notifications', fake_generate_notifications)
    with mock.patch('sentry_sdk.capture_exception') as capture_exception:
        call_command('send_daily_notifications', time=NOW)

    assert processed == [working.identifier]
    capture_exception.assert_called_once()
    failing.refresh_from_db()
    working.refresh_from_db()
    assert failing.daily_notifications_triggered_at is None
    assert working.daily_notifications_triggered_at is not None
