from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError

import pytest

from admin_site.models import Client
from users.models import User

pytestmark = pytest.mark.django_db
COMMAND_NAME='create_superuser_with_defaults'
AUTH_BACKENDS = [be.value or None for be in Client.AuthBackend]


@pytest.fixture
def test_users():
    return [
        ('Mauno', 'Koivisto'),
        ('Martti', 'Ahtisaari'),
        ('Tarja', 'Halonen'),
    ]

def make_user_kwargs(
    email_domain: str,
    user: tuple[str, str],
    organization: str,
    extra_kwargs: dict[str, str] | None = None
) -> dict[str, str]:
    first_name, last_name = user
    email = f'{first_name.lower()}.{last_name.lower()}@{email_domain}'
    kwargs = dict(
        first_name=first_name,
        last_name=last_name,
        email=email,
        organization=organization,
    )
    if extra_kwargs:
        kwargs.update(extra_kwargs)
    return kwargs

def _handle_user(domain, user_names, out, organization: str = 'TestOrg', extra_kwargs: dict | None = None):
    user_kwargs = make_user_kwargs(domain, user_names, organization, extra_kwargs)
    call_command(
        COMMAND_NAME,
        stdout=out,
        interactive=False,
        **user_kwargs,
    )
    assert 'Superuser created successfully' in out.getvalue()

    user = User.objects.get(email=user_kwargs['email'])

    auth_backend = extra_kwargs.get('auth_backend') if extra_kwargs else None
    if auth_backend:
        assert not user.has_usable_password()
        client = Client.objects.get(email_domains__domain=domain)
        assert client.auth_backend == auth_backend

    assert user.first_name == user_kwargs['first_name']
    assert user.last_name == user_kwargs['last_name']
    assert user.email == user_kwargs['email']
    assert user.person.first_name == user_kwargs['first_name']
    assert user.person.last_name == user_kwargs['last_name']
    assert user.person.email == user_kwargs['email']
    assert user.person.organization.name == organization
    user.get_adminable_plans()

def test_create_user_invalid_uuid(test_users):
    with pytest.raises(CommandError):
        _handle_user('foo.com', test_users[0], StringIO(), extra_kwargs=dict(uuid='IAmNotAValidUuid'))

def test_create_multiple_superusers_same_organization(test_users):
    out = StringIO()
    domain = 'suomi.fi'
    for user in test_users:
        _handle_user(domain, user, out)

def test_create_multiple_superusers_different_organization_same_email(test_users):
    # This use case is not supported and should throw.
    out = StringIO()
    domain = 'suomi.fi'
    for index, user in enumerate(test_users):
        if index == 0:
            _handle_user(domain, user, out, organization=f'TestOrg{index+1}')
            continue
        with pytest.raises(CommandError):
            _handle_user(domain, user, out, organization=f'TestOrg{index+1}')

def test_create_multiple_superusers_different_organization_different_email(test_users):
    out = StringIO()
    domains = ['suomi.fi', 'sverige.se', 'danmark.de']
    for index, user in enumerate(test_users):
        _handle_user(domains[index], user, out, organization=f'TestOrg{index+1}')

@pytest.mark.parametrize('auth_backend', AUTH_BACKENDS)
def test_create_user_login_methods(test_users, auth_backend):
    _handle_user('foo.com', test_users[0], StringIO(), extra_kwargs=dict(auth_backend=auth_backend))

def test_required_arguments_missing():
    out = StringIO()
    with pytest.raises(CommandError):
        call_command(COMMAND_NAME, stdout=out)
