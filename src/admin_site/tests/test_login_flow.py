from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

import pytest

from admin_site.login_method import LoginMethodError, resolve_login_method
from admin_site.models import Client
from admin_site.tests.factories import ClientPlanFactory, EmailDomainsFactory
from people.tests.factories import PersonFactory

if TYPE_CHECKING:
    from actions.models.plan import Plan
    from users.models import User

pytestmark = pytest.mark.django_db

PASSWORD = 'correct horse battery staple'  # noqa: S105


@pytest.fixture
def password_user(plan: Plan) -> User:
    person = PersonFactory.create(email='password.user@example.com', general_admin_plans=[plan])
    user = person.user
    assert user is not None
    user.set_password(PASSWORD)
    user.save()
    return user


@pytest.fixture
def sso_user(plan: Plan) -> User:
    cp = ClientPlanFactory.create(plan=plan)
    assert cp.client.auth_backend == Client.AuthBackend.AZURE_AD
    domain = EmailDomainsFactory.create(client=cp.client)
    person = PersonFactory.create(email=f'sso.user@{domain.domain}', general_admin_plans=[plan])
    user = person.user
    assert user is not None
    assert not user.has_usable_password()
    return user


class TestResolveLoginMethod:
    def test_password_user(self, password_user: User):
        result = resolve_login_method(password_user.email.upper(), None)
        assert result.method == 'password'

    def test_sso_user(self, sso_user: User):
        result = resolve_login_method(sso_user.email, None)
        assert result.method == 'azure_ad'

    def test_unknown_user(self):
        with pytest.raises(LoginMethodError) as exc_info:
            resolve_login_method('nobody@example.com', None)
        assert exc_info.value.code == 'no_user'

    def test_empty_email(self):
        with pytest.raises(LoginMethodError) as exc_info:
            resolve_login_method('  ', None)
        assert exc_info.value.code == 'invalid_email'

    def test_unresolvable_next_is_treated_as_admin(self, password_user: User):
        result = resolve_login_method(password_user.email, '/no/such/page/')
        assert result.method == 'password'


def test_check_endpoint_survives_unresolvable_next(api_client, password_user: User):
    response = api_client.post(
        reverse('admin_check_login_method'),
        {'email': password_user.email, 'next': '/no/such/page/'},
    )
    assert response.status_code == 200
    assert response.json_data['method'] == 'password'
