"""Auth-flow helpers for PublicUser SignIn/SignUp/VerifyPin mutations."""

from __future__ import annotations

from email.utils import formataddr
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.http import HttpRequest
from django.utils.translation import gettext as _
from graphql.error import GraphQLError
from strawberry.channels import ChannelsRequest

import sentry_sdk
from django_ratelimit.core import is_ratelimited  # type: ignore[import-untyped]
from loguru import logger
from starlette.requests import Request as StarletteRequest

from actions.models.plan import Plan
from actions.models.pledge import PIN_TTL, PledgeCommitment, PublicUser, PublicUserSignInAttempt
from notifications.mjml import render_mjml_from_template

if TYPE_CHECKING:
    from uuid import UUID

    from aplans.graphql_types import GQLInfo

SIGN_UP_RATE_LIMIT = '5/m'
SIGN_IN_RATE_LIMIT = '10/m'
VERIFY_PIN_RATE_LIMIT = '30/m'

logger = logger.bind(name='actions.public_user_auth')


def normalize_email(email: str) -> str:
    """Trim and lowercase an email. Raise GraphQLError if empty."""
    normalized = email.strip().lower()
    if not normalized:
        raise GraphQLError('Email is required.', extensions={'code': 'EMAIL_REQUIRED'})
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
        raise GraphQLError(
            'Too many requests, please try again later.',
            extensions={'code': 'RATE_LIMITED'},
        )


def issue_pin_for(
    public_user: PublicUser,
    anon_uuid: UUID | None = None,
    plan: Plan | None = None,
) -> None:
    """Generate a new PIN for the user, store its hash, and send it via email."""
    _, raw_pin = PublicUserSignInAttempt.create_for(public_user, anon_uuid=anon_uuid)
    send_pin_email(public_user, raw_pin, plan=plan)


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

    affected_plan_ids = set(
        PledgeCommitment.objects.filter(public_user=anon).values_list('pledge__plan_id', flat=True).distinct()
    )
    existing_pledge_ids = set(PledgeCommitment.objects.filter(public_user=verified_user).values_list('pledge_id', flat=True))
    PledgeCommitment.objects.filter(public_user=anon).exclude(pledge_id__in=existing_pledge_ids).update(public_user=verified_user)

    if anon.user_data:
        merged_user_data = {**verified_user.user_data, **anon.user_data}
        if merged_user_data != verified_user.user_data:
            verified_user.user_data = merged_user_data
            verified_user.save(update_fields=['user_data'])

    anon.delete()

    for plan in Plan.objects.filter(id__in=affected_plan_ids):
        plan.invalidate_cache()


def send_pin_email(public_user: PublicUser, raw_pin: str, plan: Plan | None = None) -> None:
    """
    Send a PIN verification code to the user's email address.

    Sent synchronously so the raw PIN never lands in the Celery broker. The
    caller should handle the case where the email delivery fails (treat it as
    a recoverable failure of the mutation that triggered it).

    The From line is always "Kausal <DEFAULT_FROM_EMAIL>" regardless of the
    plan, so users always look for the same sender. When the plan has a
    notification base template configured, the email is sent as a multipart
    message with a plan-themed HTML body; otherwise a plain-text email is sent.
    """
    if not public_user.email:
        raise ValueError('PublicUser has no email; cannot send PIN.')

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
            to=[public_user.email],
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
            to=[public_user.email],
        )
        msg.attach_alternative(html_body, 'text/html')

    msg.send(fail_silently=False)
    logger.info('Sent PIN email to public user uuid={uuid}', uuid=public_user.uuid)
