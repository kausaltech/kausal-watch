"""Auth-flow helpers for PublicUser SignIn/SignUp/VerifyPin mutations."""

from __future__ import annotations

from email.utils import formataddr
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.http import HttpRequest
from django.utils.translation import gettext as _
from graphql.error import GraphQLError
from strawberry.channels import ChannelsRequest

import sentry_sdk
from django_ratelimit.core import is_ratelimited  # type: ignore[import-untyped]
from loguru import logger
from starlette.requests import Request as StarletteRequest

from actions.models.plan import Plan
from actions.models.pledge import PledgeCommitment
from actions.models.public_user import PIN_TTL, PublicUser, PublicUserSignInAttempt
from notifications.mjml import render_mjml_from_template

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from aplans.graphql_types import GQLInfo

    from admin_site.models import Client

SIGN_UP_RATE_LIMIT = '5/m'
SIGN_IN_RATE_LIMIT = '10/m'
VERIFY_PIN_RATE_LIMIT = '30/m'

logger = logger.bind(name='actions.public_user_auth')


EMAIL_MAX_LENGTH = 254


def require_request_client(info: GQLInfo) -> Client:
    """
    Resolve the tenant that owns the current request's plan.

    Raises when the request has no plan or the plan has no primary_client set.
    All public-user auth mutations must run in a plan-hosted origin, so a
    missing client indicates the request is coming from an unconfigured site
    rather than a legitimate client user; failing loudly avoids silently
    creating client-less rows that would violate the check constraint later.
    """
    plan = info.context.request_plan
    if plan is None:
        logger.warning('public_user auth call has no request plan')
        raise GraphQLError(
            'Public user actions must originate from a plan-hosted site.',
            extensions={'code': 'NO_REQUEST_PLAN'},
        )
    client = plan.primary_client
    if client is None:
        logger.warning('plan {identifier} has no primary_client configured', identifier=plan.identifier)
        raise GraphQLError(
            'This plan is not configured for public user accounts.',
            extensions={'code': 'PLAN_HAS_NO_CLIENT'},
        )
    return client


def normalize_email(email: str) -> str:
    """Trim, lowercase, and validate an email. Raise GraphQLError on invalid input."""
    normalized = email.strip().lower()
    if not normalized:
        raise GraphQLError('Email is required.', extensions={'code': 'EMAIL_REQUIRED'})
    if len(normalized) > EMAIL_MAX_LENGTH:
        raise GraphQLError('Email address is too long.', extensions={'code': 'INVALID_EMAIL'})
    try:
        validate_email(normalized)
    except ValidationError as exc:
        raise GraphQLError('Invalid email address.', extensions={'code': 'INVALID_EMAIL'}) from exc
    return normalized


def _build_ratelimit_request(req: Any) -> Any:
    """
    Return an object django-ratelimit can read as a Django request.

    is_ratelimited only touches .method and .META (for the 'ip' key it
    reads META['REMOTE_ADDR']). For ASGI/Channels/Starlette requests
    served by Daphne, .request isn't a Django HttpRequest, so we build a
    minimal shim populated from the underlying ASGI scope. Returns the
    original request unchanged when it's already a Django HttpRequest, so
    the WSGI/sync path keeps using django-ratelimit's full IP handling
    (RATELIMIT_TRUSTED_PROXIES, RATELIMIT_IP_META, etc).
    """
    if isinstance(req, HttpRequest):
        return req
    meta: dict[str, str] = {}
    method = 'POST'
    if isinstance(req, ChannelsRequest):
        scope = req.consumer.scope
        client = scope.get('client') or ('', 0)
        meta['REMOTE_ADDR'] = client[0]
        for header_name, header_value in scope.get('headers', []):
            key = 'HTTP_' + header_name.decode('utf8').upper().replace('-', '_')
            meta[key] = header_value.decode('utf8')
        method = scope.get('method', 'POST').upper()
    elif isinstance(req, StarletteRequest):
        meta['REMOTE_ADDR'] = req.client.host if req.client else ''
        for name, value in req.headers.items():
            key = 'HTTP_' + name.upper().replace('-', '_')
            meta[key] = value
        method = req.method.upper()
    return SimpleNamespace(META=meta, method=method)


def enforce_rate_limit(info: GQLInfo, group: str, rate: str) -> None:
    """Throttle a mutation by client IP. Raises RATE_LIMITED when the limit is exceeded."""
    request = _build_ratelimit_request(info.context.request)
    if is_ratelimited(request, group=group, key='ip', rate=rate, method='POST', increment=True):
        logger.warning('rate_limited group={group}', group=group)
        raise GraphQLError(
            'Too many requests, please try again later.',
            extensions={'code': 'RATE_LIMITED'},
        )


def issue_signin_pin(
    public_user: PublicUser,
    anon_uuid: UUID | None = None,
    plan: Plan | None = None,
) -> None:
    """Generate a new PIN for an existing user and send it via email."""
    assert public_user.email is not None
    _, raw_pin = PublicUserSignInAttempt.create_for_signin(public_user, anon_uuid=anon_uuid)
    send_pin_email(public_user.email, raw_pin, plan=plan)


def issue_signup_pin(
    email: str,
    client: Client,
    terms_accepted_at: datetime,
    marketing_consented_at: datetime | None,
    anon_uuid: UUID | None = None,
    plan: Plan | None = None,
) -> None:
    """
    Generate a PIN for a pending sign-up (no PublicUser yet).

    Consent timestamps live on the attempt and are applied to the PublicUser
    at VerifyPin time, so an unverifying caller can't pre-record consent for
    someone else's mailbox.
    """
    _, raw_pin = PublicUserSignInAttempt.create_for_signup(
        email=email,
        client=client,
        terms_accepted_at=terms_accepted_at,
        marketing_consented_at=marketing_consented_at,
        anon_uuid=anon_uuid,
    )
    send_pin_email(email, raw_pin, plan=plan)


def merge_anon_into_verified(verified_user: PublicUser, anon_uuid: UUID) -> None:
    """Move pledge commitments from the anonymous PublicUser at anon_uuid into verified_user."""
    assert transaction.get_connection().in_atomic_block, 'must run inside a transaction'
    try:
        anon = PublicUser.objects.select_for_update().get(uuid=anon_uuid)
    except PublicUser.DoesNotExist:
        return
    if anon.pk == verified_user.pk:
        return
    if anon.email or anon.user_token:
        logger.warning(
            'Refusing to merge anon row uuid={uuid} into verified user pk={verified_pk}: anon row is not anonymous.',
            uuid=anon_uuid,
            verified_pk=verified_user.pk,
        )
        sentry_sdk.capture_message(
            'VerifyPin merge refused: anon_uuid points to a row past the verification boundary',
            level='warning',
        )
        return

    # Defense-in-depth against a cross-client anon_uuid: only move commitments,
    # merge user_data, and delete the anon row when the anon is same-tenant.
    # Post-RegisterPublicUser anons carry client_id directly; legacy unbound
    # rows fall back to commitment inference.
    same_client_commitments = PledgeCommitment.objects.filter(
        public_user=anon,
        pledge__plan__clients__is_primary=True,
        pledge__plan__clients__client=verified_user.client,
    )
    if anon.client_id is not None:
        is_same_client = anon.client_id == verified_user.client_id
    else:
        is_same_client = same_client_commitments.exists()
    affected_plan_ids = set(same_client_commitments.values_list('pledge__plan_id', flat=True).distinct())
    existing_pledge_ids = set(PledgeCommitment.objects.filter(public_user=verified_user).values_list('pledge_id', flat=True))
    moved = same_client_commitments.exclude(pledge_id__in=existing_pledge_ids).update(public_user=verified_user)
    # Anything still in the same-client set is a duplicate the verified user
    # already had; drop it so the anon row can be cleaned up.
    same_client_commitments.delete()
    remaining = PledgeCommitment.objects.filter(public_user=anon).count()
    if remaining:
        logger.warning(
            'Anon merge kept {remaining} cross-client commitments on anon uuid={uuid}',
            remaining=remaining,
            uuid=anon_uuid,
        )

    user_data_updated = False
    if is_same_client and anon.user_data:
        merged_user_data = {**verified_user.user_data, **anon.user_data}
        if merged_user_data != verified_user.user_data:
            verified_user.user_data = merged_user_data
            verified_user.save(update_fields=['user_data'])
            user_data_updated = True

    if is_same_client and not remaining:
        anon.delete()

    for plan in Plan.objects.filter(id__in=affected_plan_ids):
        plan.invalidate_cache()

    logger.info(
        'anon_merged verified_pk={verified_pk} moved={moved} user_data_updated={user_data_updated}',
        verified_pk=verified_user.pk,
        moved=moved,
        user_data_updated=user_data_updated,
    )


def send_pin_email(to_email: str, raw_pin: str, plan: Plan | None = None) -> None:
    """
    Send a PIN verification code to the given email address.

    Sent synchronously so the raw PIN never lands in the Celery broker. The
    caller should handle the case where the email delivery fails (treat it as
    a recoverable failure of the mutation that triggered it).

    The From line is always "Kausal <DEFAULT_FROM_EMAIL>" regardless of the
    plan, so users always look for the same sender. When the plan has a
    notification base template configured, the email is sent as a multipart
    message with a plan-themed HTML body; otherwise a plain-text email is sent.
    """
    if not to_email:
        raise ValueError('to_email is required; cannot send PIN.')

    minutes = int(PIN_TTL.total_seconds() // 60)
    base_template = getattr(plan, 'notification_base_template', None) if plan else None

    if plan is not None:
        plan_name = plan.name_i18n
        subject = _('Your sign-in code for the %(plan_name)s') % {'plan_name': plan_name}
        body_intro = _('Here is your sign-in code for the %(plan_name)s:') % {'plan_name': plan_name}
    else:
        subject = _('Your sign-in code')
        body_intro = _('Here is your sign-in code:')

    plain_body = '{intro}\n\n    {pin}\n\n{ttl}\n\n{ignore}\n\n—\n{powered_by}\nkausal.tech'.format(
        intro=body_intro,
        pin=raw_pin,
        ttl=_('Enter this code when prompted. It expires in %(minutes)d minutes.') % {'minutes': minutes},
        ignore=_("If you didn't request this code, you can ignore this email."),
        powered_by=_('Powered by Kausal Watch'),
    )

    from_email = formataddr(('Kausal', settings.DEFAULT_FROM_EMAIL))

    if plan is None or base_template is None:
        msg: EmailMessage = EmailMessage(
            subject=subject,
            body=plain_body,
            from_email=from_email,
            to=[to_email],
        )
    else:
        context = {
            'title': subject,
            'site': plan.get_site_notification_context(),
            'plan': {'name': plan_name},
            'raw_pin': raw_pin,
            'pin_ttl_minutes': minutes,
            'content_blocks': {},
            **base_template.get_notification_context(),
        }
        html_body = render_mjml_from_template('public_user_pin', context)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=plain_body,
            from_email=from_email,
            to=[to_email],
        )
        msg.attach_alternative(html_body, 'text/html')

    msg.send(fail_silently=False)
    logger.info('Sent PIN email')
