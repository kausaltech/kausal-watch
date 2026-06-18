"""Auth-flow helpers for PublicUser SignIn/SignUp/VerifyPin mutations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail import send_mail
from django.utils.translation import gettext as _
from graphql.error import GraphQLError

import sentry_sdk
from loguru import logger

from actions.models.pledge import PledgeCommitment, PublicUser, PublicUserSignInAttempt

if TYPE_CHECKING:
    from uuid import UUID

logger = logger.bind(name='actions.public_user_auth')


def normalize_email(email: str) -> str:
    """Trim and lowercase an email. Raise GraphQLError if empty."""
    normalized = email.strip().lower()
    if not normalized:
        raise GraphQLError('Email is required.')
    return normalized


def issue_pin_for(public_user: PublicUser, anon_uuid: UUID | None = None) -> None:
    """Generate a new PIN for the user, store its hash, and send it via email."""
    _, raw_pin = PublicUserSignInAttempt.create_for(public_user, anon_uuid=anon_uuid)
    send_pin_email(public_user, raw_pin)


def merge_anon_into_verified(verified_user: PublicUser, anon_uuid: UUID) -> None:
    """
    Move pledge commitments from the anonymous PublicUser at anon_uuid into verified_user.

    No-op when the anon_uuid is stale (no matching row) or when the row exists
    but has an email set (in which case it's another verified user's row and
    touching it would be an account-takeover via UUID knowledge). Duplicate
    commitments (same pledge on both rows) are removed when the anon row is
    deleted via CASCADE.
    """
    try:
        anon = PublicUser.objects.get(uuid=anon_uuid)
    except PublicUser.DoesNotExist:
        return
    if anon.pk == verified_user.pk:
        return
    if anon.email:
        logger.warning(
            'Refusing to merge anon row uuid={uuid} into verified user pk={verified_pk}: anon row has email set.',
            uuid=anon_uuid,
            verified_pk=verified_user.pk,
        )
        sentry_sdk.capture_message(
            'VerifyPin merge refused: anon_uuid points to a row with email set',
            level='warning',
        )
        return

    existing_pledge_ids = set(PledgeCommitment.objects.filter(public_user=verified_user).values_list('pledge_id', flat=True))
    PledgeCommitment.objects.filter(public_user=anon).exclude(pledge_id__in=existing_pledge_ids).update(public_user=verified_user)
    anon.delete()


def send_pin_email(public_user: PublicUser, raw_pin: str) -> None:
    """
    Send a PIN verification code to the user's email address.

    Sent synchronously so the raw PIN never lands in the Celery broker. The
    caller should handle the case where the email delivery fails (treat it as
    a recoverable failure of the mutation that triggered it).
    """
    if not public_user.email:
        raise ValueError('PublicUser has no email; cannot send PIN.')

    subject = _('Your verification code')
    body = _('Your verification code is: {pin}\n\nThe code expires in 10 minutes.').format(pin=raw_pin)

    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[public_user.email],
        fail_silently=False,
    )
    logger.info('Sent PIN email to public user uuid={uuid}', uuid=public_user.uuid)
