from __future__ import annotations

from urllib.parse import urlparse

from django.test import Client
from django.utils import timezone

import pytest

from access_requests.emails import make_set_password_url
from access_requests.models import AccessRequest
from access_requests.services import approve_access_request
from access_requests.tests.factories import AccessRequestFactory
from actions.tests.factories import PlanFactory
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db

NEW_PASSWORD = 'correct-horse-battery-staple'  # noqa: S105


@pytest.fixture
def plan(settings):
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
    return PlanFactory.create(identifier='plan', site_url='https://plan.example.com', features__enable_access_requests=True)


@pytest.fixture
def approved(plan):
    admin = PersonFactory.create(general_admin_plans=[plan]).user
    assert admin is not None
    req = AccessRequestFactory.create(plan=plan, email='visitor@example.com')
    return approve_access_request(req, by=admin)


def _user(req: AccessRequest):
    assert req.person is not None
    user = req.person.user
    assert user is not None
    return user


def _path(url: str) -> str:
    return urlparse(url).path


def _open_form(client: Client, req: AccessRequest) -> str:
    url = make_set_password_url(req)
    assert url is not None
    response = client.get(_path(url))
    assert response.status_code == 302
    return response['Location']


class TestSetPasswordUrl:
    def test_is_given_to_a_fresh_user(self, approved):
        assert make_set_password_url(approved) is not None

    def test_is_not_given_to_a_user_without_a_password(self, approved):
        user = _user(approved)
        user.set_unusable_password()
        user.save()
        assert make_set_password_url(approved) is None

    def test_is_not_given_to_a_user_who_has_signed_in(self, approved):
        user = _user(approved)
        user.last_login = timezone.now()
        user.save()
        assert make_set_password_url(approved) is None

    def test_is_not_given_for_a_pending_request(self, plan):
        req = AccessRequestFactory.create(plan=plan)
        assert make_set_password_url(req) is None


class TestSetPasswordView:
    def test_sets_the_password_signs_in_and_goes_to_the_plan(self, client, approved):
        form_url = _open_form(client, approved)

        response = client.post(form_url, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})

        assert response.status_code == 302
        assert response['Location'] == 'https://plan.example.com/access-approved'
        user = _user(approved)
        user.refresh_from_db()
        assert user.check_password(NEW_PASSWORD)
        assert client.session['_auth_user_id'] == str(user.pk)

    def test_link_works_once(self, client, approved):
        url = make_set_password_url(approved)
        assert url is not None
        form_url = _open_form(client, approved)
        client.post(form_url, {'new_password1': NEW_PASSWORD, 'new_password2': NEW_PASSWORD})

        response = Client().get(_path(url))

        assert response.status_code == 200
        assert not response.context['validlink']

    def test_invalid_password_is_not_set(self, client, approved):
        form_url = _open_form(client, approved)

        response = client.post(form_url, {'new_password1': 'short', 'new_password2': 'short'})

        assert response.status_code == 200
        assert response.context['form'].errors
        user = _user(approved)
        user.refresh_from_db()
        assert not user.check_password('short')

    def test_link_of_another_request_is_refused(self, client, plan, approved):
        url = make_set_password_url(approved)
        assert url is not None
        other = AccessRequestFactory.create(plan=plan, status=AccessRequest.Status.APPROVED)
        tampered = _path(url).replace(f'/{approved.pk}/', f'/{other.pk}/')

        response = client.get(tampered)

        assert response.status_code == 200
        assert not response.context['validlink']

    def test_rejected_request_is_refused(self, client, approved):
        url = make_set_password_url(approved)
        assert url is not None
        AccessRequest.objects.filter(pk=approved.pk).update(status=AccessRequest.Status.REJECTED)

        response = client.get(_path(url))

        assert response.status_code == 200
        assert not response.context['validlink']

    def test_is_in_the_plan_language(self, client, plan, approved):
        plan.primary_language = 'fi'
        plan.other_languages = ['en']
        plan.save()
        form_url = _open_form(client, approved)

        response = client.get(form_url)

        assert response.status_code == 200
        assert 'lang="fi"' in response.content.decode()
