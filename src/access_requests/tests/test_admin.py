from __future__ import annotations

import re
from datetime import timedelta
from unittest.mock import patch

from django.contrib.messages import get_messages
from django.core import mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

import pytest

from access_requests.models import AccessRequest
from access_requests.tests.factories import AccessRequestFactory
from actions.models import PlanFeatures
from actions.tests.factories import ActionFactory, PlanFactory
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def plan():
    return PlanFactory.create(features__enable_access_requests=True)


@pytest.fixture
def plan_admin_user(plan):
    return PersonFactory.create(general_admin_plans=[plan]).user


@pytest.fixture
def contact_person_user(plan):
    """Someone with admin access to the plan who is not a plan admin."""
    return PersonFactory.create(contact_for_actions=[ActionFactory.create(plan=plan)]).user


@pytest.fixture
def admin_client(client, plan_admin_user):
    client.force_login(plan_admin_user)
    return client


def _home(client):
    response = client.get(reverse('wagtailadmin_home'))
    assert response.status_code == 200
    return response.content.decode()


def _messages(response):
    return [str(m).strip() for m in get_messages(response.wsgi_request)]


def assert_permission_denied(response):
    # The Wagtail admin answers PermissionDenied with a redirect home and an error message.
    assert response.status_code == 302
    assert _messages(response) == ['Sorry, you do not have permission to access this area.']


class TestPanel:
    def test_lists_pending_requests_with_previous_rejection(self, admin_client, plan):
        now = timezone.now()
        rejected = AccessRequestFactory.create(plan=plan, email='again@example.com', status=AccessRequest.Status.REJECTED)
        AccessRequest.objects.filter(pk=rejected.pk).update(
            created_at=now - timedelta(days=20), decided_at=now - timedelta(days=13)
        )
        AccessRequestFactory.create(plan=plan, email='again@example.com')
        AccessRequestFactory.create(plan=plan, email='first@example.com')
        AccessRequestFactory.create(plan=plan, email='approved@example.com', status=AccessRequest.Status.APPROVED)

        html = _home(admin_client)

        assert 'Access requests' in html
        assert '2 waiting' in html
        assert 'first@example.com' in html
        assert 'again@example.com' in html
        assert 'Requested again' in html
        assert 'approved@example.com' not in html
        # Rejecting is confirmed in a dialog, one per row; approving is not.
        assert html.count('Reject access request?') == 2
        assert 'will receive an email saying their request has been rejected' in html

    def test_shows_empty_state(self, admin_client, plan):
        html = _home(admin_client)
        assert 'Access requests' in html
        assert 'No access requests waiting' in html

    def test_hidden_when_the_plan_takes_no_requests(self, admin_client, plan):
        PlanFeatures.objects.filter(plan=plan).update(enable_access_requests=False)
        assert 'Access requests' not in _home(admin_client)

    def test_hidden_from_users_who_are_not_plan_admins(self, client, plan, contact_person_user):
        AccessRequestFactory.create(plan=plan, email='visitor@example.com')
        client.force_login(contact_person_user)
        html = _home(client)
        assert 'visitor@example.com' not in html

    def test_paginates_oldest_first(self, admin_client, plan):
        now = timezone.now()
        for i in range(12):
            req = AccessRequestFactory.create(plan=plan, email=f'visitor{i:02}@example.com')
            AccessRequest.objects.filter(pk=req.pk).update(created_at=now - timedelta(hours=100 - i))

        first_page = _home(admin_client)
        assert 'visitor00@example.com' in first_page
        assert 'visitor11@example.com' not in first_page

        second_page = admin_client.get(reverse('wagtailadmin_home'), {'access_requests_page': 2}).content.decode()
        assert 'visitor11@example.com' in second_page
        assert 'visitor00@example.com' not in second_page


class TestDecide:
    def test_approve(self, admin_client, plan, plan_admin_user):
        req = AccessRequestFactory.create(plan=plan, email='visitor@example.com')
        mail.outbox.clear()

        response = admin_client.post(reverse('access_requests_approve', args=[req.pk]))

        assert response.status_code == 302
        assert response['Location'] == reverse('wagtailadmin_home')
        req.refresh_from_db()
        assert req.status == AccessRequest.Status.APPROVED
        assert req.decided_by == plan_admin_user
        assert [m.to for m in mail.outbox] == [['visitor@example.com']]
        assert _messages(response) == ['Access approved for visitor@example.com. They have been notified by email.']

    def test_reject(self, admin_client, plan):
        req = AccessRequestFactory.create(plan=plan, email='visitor@example.com')
        mail.outbox.clear()

        response = admin_client.post(reverse('access_requests_reject', args=[req.pk]))

        assert response.status_code == 302
        req.refresh_from_db()
        assert req.status == AccessRequest.Status.REJECTED
        assert [m.to for m in mail.outbox] == [['visitor@example.com']]
        assert _messages(response) == ['Access request from visitor@example.com rejected. They have been notified by email.']

    @pytest.mark.parametrize('action', ['approve', 'reject'])
    def test_get_is_not_allowed(self, admin_client, plan, action):
        req = AccessRequestFactory.create(plan=plan)
        response = admin_client.get(reverse(f'access_requests_{action}', args=[req.pk]))
        assert response.status_code == 405
        req.refresh_from_db()
        assert req.status == AccessRequest.Status.PENDING

    @pytest.mark.parametrize('action', ['approve', 'reject'])
    def test_request_of_another_plan_is_forbidden(self, admin_client, action):
        req = AccessRequestFactory.create(plan=PlanFactory.create(features__enable_access_requests=True))
        response = admin_client.post(reverse(f'access_requests_{action}', args=[req.pk]))
        assert_permission_denied(response)
        req.refresh_from_db()
        assert req.status == AccessRequest.Status.PENDING

    @pytest.mark.parametrize('action', ['approve', 'reject'])
    def test_non_admin_is_forbidden(self, client, plan, contact_person_user, action):
        req = AccessRequestFactory.create(plan=plan)
        client.force_login(contact_person_user)
        response = client.post(reverse(f'access_requests_{action}', args=[req.pk]))
        assert_permission_denied(response)
        req.refresh_from_db()
        assert req.status == AccessRequest.Status.PENDING

    def test_already_decided_request_is_not_emailed_again(self, admin_client, plan):
        req = AccessRequestFactory.create(plan=plan, email='visitor@example.com', status=AccessRequest.Status.APPROVED)
        mail.outbox.clear()

        response = admin_client.post(reverse('access_requests_reject', args=[req.pk]))

        assert response.status_code == 302
        req.refresh_from_db()
        assert req.status == AccessRequest.Status.APPROVED
        assert mail.outbox == []
        assert _messages(response) == ['The access request from visitor@example.com was already handled.']

    def test_undelivered_email_is_reported(self, admin_client, plan):
        req = AccessRequestFactory.create(plan=plan, email='visitor@example.com')
        with patch('access_requests.views.send_decision_email', return_value=False):
            response = admin_client.post(reverse('access_requests_approve', args=[req.pk]))
        req.refresh_from_db()
        assert req.status == AccessRequest.Status.APPROVED
        assert _messages(response) == ['Access approved for visitor@example.com, but the email to them could not be sent.']


@pytest.mark.parametrize(
    ('action', 'status'), [('approve', AccessRequest.Status.APPROVED), ('reject', AccessRequest.Status.REJECTED)]
)
def test_panel_forms_pass_csrf_checks(plan, plan_admin_user, action, status):
    # The test client skips CSRF checks unless told otherwise; a browser does not.
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(plan_admin_user)
    req = AccessRequestFactory.create(plan=plan)
    html = csrf_client.get(reverse('wagtailadmin_home')).content.decode()

    action_url = reverse(f'access_requests_{action}', args=[req.pk])
    form = html[html.index(f'action="{action_url}"') :]
    match = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', form[: form.index('</form>')])
    assert match is not None, 'the form carries no CSRF token'

    response = csrf_client.post(action_url, {'csrfmiddlewaretoken': match.group(1)})

    assert response.status_code == 302
    req.refresh_from_db()
    assert req.status == status
