from __future__ import annotations

import re
import subprocess
from unittest.mock import patch
from urllib.parse import urlparse

from django.core import mail
from django.core.mail import EmailMultiAlternatives
from django.urls import resolve
from django.utils import timezone

import pytest

from access_requests.emails import send_decision_email
from access_requests.models import AccessRequest
from access_requests.services import approve_access_request
from access_requests.tests.factories import AccessRequestFactory
from actions.tests.factories import PlanFactory
from notifications.models import BaseTemplate
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db


def _approved(plan, **kwargs):
    return AccessRequestFactory.create(plan=plan, status=AccessRequest.Status.APPROVED, **kwargs)


def _approved_through_service(plan):
    admin = PersonFactory.create(general_admin_plans=[plan]).user
    assert admin is not None
    return approve_access_request(AccessRequestFactory.create(plan=plan), by=admin)


def _user(req):
    assert req.person is not None
    assert req.person.user is not None
    return req.person.user


def _rejected(plan, **kwargs):
    return AccessRequestFactory.create(plan=plan, status=AccessRequest.Status.REJECTED, **kwargs)


@pytest.fixture
def plan():
    return PlanFactory.create(
        name='Example Climate Plan',
        site_url='https://plan.example.com',
        access_request_contact_email='access@example.com',
        access_request_eligibility_text='Access is only given to staff of the ministry.',
    )


class TestApproved:
    def test_tells_the_visitor_where_to_sign_in(self, plan):
        req = _approved(plan, email='visitor@example.com')
        mail.outbox.clear()

        assert send_decision_email(req) is True

        [msg] = mail.outbox
        assert msg.to == ['visitor@example.com']
        assert msg.subject == 'Your access to Example Climate Plan has been approved'
        assert 'https://plan.example.com' in msg.body

    def test_gives_a_fresh_user_a_link_to_set_their_password(self, plan):
        req = _approved_through_service(plan)
        mail.outbox.clear()

        send_decision_email(req)

        [msg] = mail.outbox
        [url] = re.findall(r'http\S+/access-requests/\S+/', str(msg.body))
        assert resolve(urlparse(url).path).url_name == 'access_requests_set_password'
        assert 'expires in 3 days' in msg.body
        assert 'You can sign in at' not in msg.body

    def test_gives_no_link_to_an_sso_user(self, plan):
        req = _approved_through_service(plan)
        user = _user(req)
        user.set_unusable_password()
        user.save()
        mail.outbox.clear()

        send_decision_email(req)

        [msg] = mail.outbox
        assert '/access-requests/' not in msg.body
        assert 'You can sign in at https://plan.example.com with this email address.' in msg.body
        assert 'Sign in: https://plan.example.com' in msg.body

    def test_gives_no_link_to_someone_who_has_signed_in(self, plan):
        req = _approved_through_service(plan)
        user = _user(req)
        user.last_login = timezone.now()
        user.save()
        mail.outbox.clear()

        send_decision_email(req)

        [msg] = mail.outbox
        assert '/access-requests/' not in msg.body

    def test_leaves_out_the_address_when_the_plan_has_no_site_url(self, plan):
        plan.site_url = None
        plan.save()
        req = _approved(plan)
        mail.outbox.clear()

        send_decision_email(req)

        [msg] = mail.outbox
        assert 'None' not in msg.body
        assert 'You can sign in with this email address.' in msg.body

    def test_is_in_the_plan_language(self, plan):
        plan.primary_language = 'fi'
        plan.other_languages = ['en']
        plan.name_en = 'Example Climate Plan'
        plan.name = 'Esimerkkisuunnitelma'
        plan.save()
        req = _approved(plan)
        mail.outbox.clear()

        send_decision_email(req)

        [msg] = mail.outbox
        assert 'Esimerkkisuunnitelma' in msg.subject


class TestRejected:
    def test_names_who_may_have_access_and_whom_to_ask(self, plan):
        req = _rejected(plan, email='visitor@example.com')
        mail.outbox.clear()

        assert send_decision_email(req) is True

        [msg] = mail.outbox
        assert msg.to == ['visitor@example.com']
        assert msg.subject == 'Your request to access Example Climate Plan'
        assert 'not been approved' in msg.body
        assert 'Access is only given to staff of the ministry.' in msg.body
        assert 'access@example.com' in msg.body

    def test_leaves_out_the_contact_sentence_without_a_contact_address(self, plan):
        plan.access_request_contact_email = ''
        plan.save()
        req = _rejected(plan)
        mail.outbox.clear()

        send_decision_email(req)

        [msg] = mail.outbox
        assert 'contact' not in msg.body.lower()


@pytest.mark.parametrize('status', [AccessRequest.Status.APPROVED, AccessRequest.Status.REJECTED])
def test_attaches_plan_themed_html_when_the_plan_has_a_base_template(plan, status):
    BaseTemplate.objects.create(plan=plan, brand_dark_color='#123456')
    plan.refresh_from_db()
    req = AccessRequestFactory.create(plan=plan, status=status)
    mail.outbox.clear()

    # The MJML compiler is not needed to check that the template renders with the context given.
    with patch('access_requests.emails.render_mjml', side_effect=lambda mjml: mjml):
        send_decision_email(req)

    [msg] = mail.outbox
    assert isinstance(msg, EmailMultiAlternatives)
    [(html, mimetype)] = msg.alternatives
    assert mimetype == 'text/html'
    assert '#123456' in str(html)
    assert 'Example Climate Plan' in str(html)


def test_html_has_a_button_to_set_the_password(plan):
    BaseTemplate.objects.create(plan=plan)
    plan.refresh_from_db()
    req = _approved_through_service(plan)
    mail.outbox.clear()

    with patch('access_requests.emails.render_mjml', side_effect=lambda mjml: mjml):
        send_decision_email(req)

    [msg] = mail.outbox
    assert isinstance(msg, EmailMultiAlternatives)
    [url] = re.findall(r'http\S+/access-requests/\S+/', str(msg.body))
    [(html, _mimetype)] = msg.alternatives
    assert f'<mj-button align="left" href="{url}">Set your password</mj-button>' in str(html)


def test_admin_entered_text_is_escaped_in_the_html(plan):
    BaseTemplate.objects.create(plan=plan)
    plan.access_request_eligibility_text = 'Only staff of <department> & partners'
    plan.save()
    plan.refresh_from_db()
    req = _rejected(plan)
    mail.outbox.clear()

    with patch('access_requests.emails.render_mjml', side_effect=lambda mjml: mjml):
        send_decision_email(req)

    [msg] = mail.outbox
    assert isinstance(msg, EmailMultiAlternatives)
    [(html, _mimetype)] = msg.alternatives
    assert 'Only staff of &lt;department&gt; &amp; partners' in str(html)
    assert '<department>' not in str(html)


def test_pending_request_is_not_emailed(plan):
    req = AccessRequestFactory.create(plan=plan)
    with pytest.raises(ValueError, match='pending'):
        send_decision_email(req)


def test_delivery_failure_is_reported_not_raised(plan):
    req = _approved(plan)
    with (
        patch('access_requests.emails.EmailSender.send_all', side_effect=OSError('connection refused')),
        patch('access_requests.emails.sentry_sdk.capture_exception') as captured,
    ):
        assert send_decision_email(req) is False
    captured.assert_called_once()


def test_rendering_failure_is_reported_not_raised(plan):
    BaseTemplate.objects.create(plan=plan)
    plan.refresh_from_db()
    req = _approved(plan)
    mail.outbox.clear()
    with (
        patch('access_requests.emails.render_mjml', side_effect=subprocess.CalledProcessError(1, 'mjml')),
        patch('access_requests.emails.sentry_sdk.capture_exception') as captured,
    ):
        assert send_decision_email(req) is False
    captured.assert_called_once()
    assert mail.outbox == []
