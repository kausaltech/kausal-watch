from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

import pytest

from access_requests.models import AccessRequest
from access_requests.tests.factories import AccessRequestFactory
from actions.tests.factories import PlanFactory

pytestmark = pytest.mark.django_db


def test_only_one_pending_request_per_email_per_plan():
    plan = PlanFactory.create()
    AccessRequestFactory.create(plan=plan, email='visitor@example.com')
    with pytest.raises(IntegrityError), transaction.atomic():
        AccessRequestFactory.create(plan=plan, email='visitor@example.com')


def test_same_email_may_have_pending_requests_in_different_plans():
    AccessRequestFactory.create(email='visitor@example.com')
    AccessRequestFactory.create(email='visitor@example.com')
    assert AccessRequest.objects.count() == 2


def test_request_again_after_rejection_creates_new_row():
    plan = PlanFactory.create()
    AccessRequestFactory.create(plan=plan, email='visitor@example.com', status=AccessRequest.Status.REJECTED)
    AccessRequestFactory.create(plan=plan, email='visitor@example.com')
    assert AccessRequest.objects.filter(plan=plan).count() == 2


def test_pending_is_oldest_first():
    plan = PlanFactory.create()
    newer = AccessRequestFactory.create(plan=plan)
    older = AccessRequestFactory.create(plan=plan)
    AccessRequest.objects.filter(pk=older.pk).update(created_at=timezone.now() - timedelta(days=3))
    AccessRequestFactory.create(plan=plan, status=AccessRequest.Status.APPROVED)
    assert list(AccessRequest.objects.qs.pending()) == [older, newer]


def test_with_previous_rejection_annotates_latest_earlier_rejection():
    plan = PlanFactory.create()
    now = timezone.now()
    first = AccessRequestFactory.create(plan=plan, email='visitor@example.com', status=AccessRequest.Status.REJECTED)
    second = AccessRequestFactory.create(plan=plan, email='visitor@example.com', status=AccessRequest.Status.REJECTED)
    AccessRequest.objects.filter(pk=first.pk).update(created_at=now - timedelta(days=20), decided_at=now - timedelta(days=19))
    AccessRequest.objects.filter(pk=second.pk).update(created_at=now - timedelta(days=10), decided_at=now - timedelta(days=9))
    current = AccessRequestFactory.create(plan=plan, email='visitor@example.com')
    # A rejection of the same address in another plan does not count.
    other = AccessRequestFactory.create(email='visitor@example.com', status=AccessRequest.Status.REJECTED)
    AccessRequest.objects.filter(pk=other.pk).update(decided_at=now - timedelta(days=1))
    fresh = AccessRequestFactory.create(plan=plan)

    annotated = {r.pk: r for r in AccessRequest.objects.qs.pending().with_previous_rejection()}

    second.refresh_from_db()
    assert annotated[current.pk].previously_rejected_at == second.decided_at
    assert annotated[fresh.pk].previously_rejected_at is None
