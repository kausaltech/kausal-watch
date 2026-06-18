"""Auth-flow helpers for PublicUser SignIn/SignUp/VerifyPin mutations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import settings
from django.core.mail import send_mail
from django.utils.translation import gettext as _
from graphql.error import GraphQLError

from loguru import logger

from actions.models.pledge import PublicUserSignInAttempt

if TYPE_CHECKING:
    from uuid import UUID

    from actions.models.pledge import PublicUser

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
