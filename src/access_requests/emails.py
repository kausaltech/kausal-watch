"""
Emails telling a visitor how their access request was decided.

Sent synchronously after the decision has been committed, so the admin who decided can be told
right away when an email could not be delivered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.urls import reverse
from django.utils import translation
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext as _

import sentry_sdk
from loguru import logger

from aplans.email_sender import EmailSender

from notifications.mjml import make_jinja_environment, render_mjml

from .models import AccessRequest

if TYPE_CHECKING:
    from actions.models import Plan
    from users.models import User

logger = logger.bind(name='access_requests.emails')


def get_plan_url(plan: Plan) -> str | None:
    """Return the public URL of the plan's site, or None when no hostname can be resolved for it."""
    try:
        return plan.get_view_url()
    except ValueError:
        return None


def may_set_password(req: AccessRequest, user: User | None, plan_url: str | None) -> bool:
    """
    Tell whether `user` may set their password through the approval of `req`.

    Nobody who signs in some other way may: an SSO user has no usable password, and someone who
    has signed in before already has their credentials and did not ask for a reset. The plan must
    have a site to send them to afterwards; `plan_url` is its URL, as `get_plan_url()` returns it.
    """
    if req.status != AccessRequest.Status.APPROVED or req.person is None or not plan_url:
        return False
    if user is None or req.person.user != user:
        return False
    if not user.is_active or user.is_superuser:
        return False
    return user.has_usable_password() and user.last_login is None


def make_set_password_url(req: AccessRequest, plan_url: str | None) -> str | None:
    """Return a one-time link for the approved requester to set their password, if they may."""
    user = req.person.user if req.person is not None else None
    if user is None or not may_set_password(req, user, plan_url):
        return None
    kwargs = {
        'pk': req.pk,
        'uidb64': urlsafe_base64_encode(force_bytes(user.pk)),
        'token': default_token_generator.make_token(user),
    }
    return f'{settings.ADMIN_BASE_URL}{reverse("access_requests_set_password", kwargs=kwargs)}'


class _Button(TypedDict):
    label: str
    url: str


class _Content(TypedDict):
    subject: str
    heading: str
    paragraphs: list[str]
    button: NotRequired[_Button]


def _approved_content(req: AccessRequest, plan_name: str, plan_url: str | None) -> _Content:
    set_password_url = make_set_password_url(req, plan_url)
    content: _Content = {
        'subject': _('Your access to %(plan_name)s has been approved') % {'plan_name': plan_name},
        'heading': _('Your access has been approved'),
        'paragraphs': [
            _('Your request to view %(plan_name)s has been approved.') % {'plan_name': plan_name},
        ],
    }

    if set_password_url is None:
        if not plan_url:
            content['paragraphs'].append(_('You can sign in with this email address.'))
            return content
        content['paragraphs'].append(_('You can sign in at %(plan_url)s with this email address.') % {'plan_url': plan_url})
        content['button'] = {'label': _('Sign in'), 'url': plan_url}
        return content
    days = int(settings.PASSWORD_RESET_TIMEOUT / (60 * 60 * 24))
    content['paragraphs'].append(
        _('First, set your password with the link below. The link works once and expires in %(days)s days.') % {'days': days}
    )
    content['button'] = {'label': _('Set your password'), 'url': set_password_url}
    return content


def _rejected_content(req: AccessRequest, plan_name: str) -> _Content:
    plan = req.plan
    paragraphs = [_('Your request to view %(plan_name)s has not been approved.') % {'plan_name': plan_name}]
    if plan.access_request_eligibility_text_i18n:
        paragraphs.append(plan.access_request_eligibility_text_i18n)
    if plan.access_request_contact_email:
        paragraphs.append(
            _('If you think this is a mistake, or you need access for your work, please contact %(email)s.')
            % {'email': plan.access_request_contact_email}
        )
    return {
        'subject': _('Your request to access %(plan_name)s') % {'plan_name': plan_name},
        'heading': _('Your request was not approved'),
        'paragraphs': paragraphs,
    }


def _site_context(plan: Plan, plan_url: str | None) -> dict[str, str]:
    general_content = getattr(plan, 'general_content', None)
    return {
        'view_url': plan_url or '',
        'title': (general_content.site_title if general_content else '') or plan.name_i18n,
    }


def _build_message(req: AccessRequest) -> EmailMessage:
    plan = req.plan
    plan_name = plan.name_i18n
    plan_url = get_plan_url(plan)
    if req.status == AccessRequest.Status.APPROVED:
        content = _approved_content(req, plan_name, plan_url)
    elif req.status == AccessRequest.Status.REJECTED:
        content = _rejected_content(req, plan_name)
    else:
        raise ValueError(f'Access request {req.pk} is still pending')

    footer = _('You are receiving this email because an access request was made for this address on %(plan_name)s.') % {
        'plan_name': plan_name
    }
    button = content.get('button')
    button_lines = [f'{button["label"]}: {button["url"]}'] if button else []
    plain_body = '\n\n'.join([_('Hi,'), *content['paragraphs'], *button_lines, '—', footer, _('Powered by Kausal Watch')])

    base_template = getattr(plan, 'notification_base_template', None)
    if base_template is None:
        return EmailMessage(subject=content['subject'], body=plain_body, to=[req.email])

    context = {
        'title': content['heading'],
        'site': _site_context(plan, plan_url),
        'paragraphs': content['paragraphs'],
        'button': button,
        'footer': footer,
        'content_blocks': {},
        **base_template.get_notification_context(),
    }
    template = make_jinja_environment().get_template('access_request_decided.mjml')
    html_body = render_mjml(template.render(context))
    msg = EmailMultiAlternatives(subject=content['subject'], body=plain_body, to=[req.email])
    msg.attach_alternative(html_body, 'text/html')
    return msg


def send_decision_email(req: AccessRequest) -> bool:
    """
    Email the requester how their request was decided; return whether it was sent.

    A failure is reported to Sentry rather than raised: the decision stands either way.
    """
    plan = req.plan
    if req.status == AccessRequest.Status.PENDING:
        raise ValueError(f'Access request {req.pk} is still pending')
    try:
        with translation.override(plan.primary_language):
            msg = _build_message(req)
        sender = EmailSender(plan)
        sender.queue(msg)
        sender.send_all()
    except Exception as e:
        sentry_sdk.capture_exception(e)
        logger.error(f'Could not send the decision email of access request {req.pk}')
        return False
    logger.info(f'Sent the decision email of access request {req.pk}')
    return True
