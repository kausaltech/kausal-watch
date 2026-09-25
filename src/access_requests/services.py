"""
State changes of access requests.

Every change goes through here, so the admin views and the GraphQL mutation cannot disagree about
what approving or rejecting means.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import IntegrityError, transaction
from django.utils import timezone

from loguru import logger

from actions.models import PlanPublicSiteViewer
from people.models import Person
from users.models import User

from .models import AccessRequest

if TYPE_CHECKING:
    from actions.models import Plan

logger = logger.bind(name='access_requests.services')


class AccessRequestNotPendingError(Exception):
    """The request was already decided, e.g. by another admin in another tab."""


def normalize_email(email: str) -> str:
    return email.strip().lower()


def create_access_request(plan: Plan, email: str, first_name: str = '', last_name: str = '') -> None:
    """
    Record that `email` asks to read `plan`, unless that would change nothing.

    Returns nothing on purpose: whether a request was created, was already pending or was not
    needed must not be observable by the caller, since the address is not verified.
    """
    email = normalize_email(email)
    user = User.objects.filter(email__iexact=email, is_active=True).first()
    if user is not None and user.can_access_public_site(plan):
        return
    if AccessRequest.objects.qs.pending().filter(plan=plan, email=email).exists():
        return
    try:
        with transaction.atomic():
            AccessRequest.objects.create(plan=plan, email=email, first_name=first_name, last_name=last_name)
    except IntegrityError:
        # A simultaneous request from the same address won the race; one pending request is enough.
        return


def _lock_pending(req: AccessRequest) -> AccessRequest:
    locked = AccessRequest.objects.select_for_update().select_related('plan').get(pk=req.pk)
    if locked.status != AccessRequest.Status.PENDING:
        raise AccessRequestNotPendingError(str(locked))
    return locked


def _get_or_create_person(req: AccessRequest, by: User) -> Person:
    person = Person.objects.filter(email__iexact=req.email).first()
    if person is not None:
        return person
    person = Person(
        email=req.email,
        first_name=req.first_name,
        last_name=req.last_name,
        organization=req.plan.organization,
        created_by=by,
    )
    # Saving also creates the corresponding user.
    person.save()
    return person


@transaction.atomic
def approve_access_request(req: AccessRequest, by: User) -> AccessRequest:
    """Grant the requester access to the plan's public site, and nothing more."""
    req = _lock_pending(req)
    plan = req.plan
    person = _get_or_create_person(req, by)
    user = person.user
    # The person form reads a viewer row as "public site only" and would hide the admin rights of
    # someone who already has them, so they get no row: they can read the plan already.
    if user is None or not user.can_access_admin(plan):
        PlanPublicSiteViewer.objects.get_or_create(plan=plan, person=person)
    req.status = AccessRequest.Status.APPROVED
    req.decided_at = timezone.now()
    req.decided_by = by
    req.person = person
    req.save(update_fields=['status', 'decided_at', 'decided_by', 'person'])
    logger.info(f'Access request {req.pk} to plan {plan.pk} approved')
    return req


@transaction.atomic
def reject_access_request(req: AccessRequest, by: User) -> AccessRequest:
    req = _lock_pending(req)
    req.status = AccessRequest.Status.REJECTED
    req.decided_at = timezone.now()
    req.decided_by = by
    req.save(update_fields=['status', 'decided_at', 'decided_by'])
    logger.info(f'Access request {req.pk} to plan {req.plan_id} rejected')
    return req
