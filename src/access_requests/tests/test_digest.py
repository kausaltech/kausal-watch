"""The daily email telling plan admins about new access requests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from django.core import mail

import pytest

from access_requests.models import AccessRequest
from access_requests.tests.factories import AccessRequestFactory
from actions.models import PlanFeatures
from actions.tests.factories import PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from notifications.management.commands.send_plan_notifications import NotificationEngine
from notifications.models import AutomaticNotificationTemplate, BaseTemplate
from notifications.notifications import NotificationType
from notifications.tests.factories import AutomaticNotificationTemplateFactory
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db

DIGEST = NotificationType.ACCESS_REQUESTS_RECEIVED
PLAN_BRAND_COLOR = '#aa0011'


@pytest.fixture
def plan():
    plan = PlanFactory.create(name='Example Climate Plan', features__enable_access_requests=True)
    AutomaticNotificationTemplateFactory.create(
        base__plan=plan,
        base__brand_dark_color=PLAN_BRAND_COLOR,
        type=DIGEST.identifier,
        send_to_plan_admins=True,
        send_to_custom_email=False,
        custom_email='',
    )
    # Recipients' emails link to the admin of the plan's client.
    ClientPlanFactory.create(plan=plan)
    plan.refresh_from_db()
    return plan


@pytest.fixture
def admin(plan):
    return PersonFactory.create(email='admin@example.com', general_admin_plans=[plan])


def _run(plan, now):
    NotificationEngine(plan, only_type=DIGEST.identifier, now=now).generate_notifications()


def _now(plan, day=1):
    return plan.to_local_timezone(datetime(2000, 1, day, 9, 0, tzinfo=UTC))


def test_lists_new_requests_to_plan_admins(plan, admin):
    AccessRequestFactory.create(plan=plan, email='first@example.com')
    AccessRequestFactory.create(plan=plan, email='second@example.com')
    AccessRequestFactory.create(plan=plan, email='decided@example.com', status=AccessRequest.Status.REJECTED)
    mail.outbox.clear()

    _run(plan, _now(plan))

    [msg] = mail.outbox
    assert msg.to == ['admin@example.com']
    assert 'first@example.com' in msg.body
    assert 'second@example.com' in msg.body
    assert 'decided@example.com' not in msg.body
    assert '2 requests are waiting for review in total' in msg.body


def test_uses_admin_branding_rather_than_the_plan_theme(plan, admin):
    AccessRequestFactory.create(plan=plan)
    mail.outbox.clear()

    _run(plan, _now(plan))

    [msg] = mail.outbox
    assert PLAN_BRAND_COLOR not in msg.body
    assert 'Kausal Watch' in msg.body


def test_each_request_is_announced_once_but_counted_while_waiting(plan, admin):
    AccessRequestFactory.create(plan=plan, email='first@example.com')
    _run(plan, _now(plan, day=1))
    mail.outbox.clear()

    _run(plan, _now(plan, day=2))
    assert mail.outbox == []

    AccessRequestFactory.create(plan=plan, email='second@example.com')
    _run(plan, _now(plan, day=3))
    [msg] = mail.outbox
    assert 'second@example.com' in msg.body
    assert 'first@example.com' not in msg.body
    assert '2 requests are waiting for review in total' in msg.body


def test_nothing_is_sent_when_the_plan_takes_no_requests(plan, admin):
    PlanFeatures.objects.filter(plan=plan).update(enable_access_requests=False)
    plan.refresh_from_db()
    AccessRequestFactory.create(plan=plan)
    mail.outbox.clear()

    _run(plan, _now(plan))

    assert mail.outbox == []


def test_template_is_seeded_when_the_feature_is_switched_on():
    plan = PlanFactory.create()
    BaseTemplate.objects.create(plan=plan)
    assert not AutomaticNotificationTemplate.objects.filter(base__plan=plan, type=DIGEST.identifier).exists()

    features = PlanFeatures.objects.get(plan=plan)
    features.enable_access_requests = True
    features.save()

    template = AutomaticNotificationTemplate.objects.get(base__plan=plan, type=DIGEST.identifier)
    assert template.send_to_plan_admins


def test_request_filed_after_a_run_is_in_the_next_digest(plan, admin):
    _run(plan, _now(plan, day=1))
    AccessRequestFactory.create(plan=plan, email='late@example.com')
    mail.outbox.clear()
    _run(plan, _now(plan, day=1) + timedelta(days=1))
    [msg] = mail.outbox
    assert 'late@example.com' in msg.body
