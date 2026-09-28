from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from django.urls import Resolver404, resolve
from django.utils.translation import gettext as _

from users.models import User


@dataclass(frozen=True)
class LoginMethod:
    method: str


class LoginMethodError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _next_is_public_site(next_url: str | None) -> bool:
    if not next_url:
        return False
    try:
        resolved = resolve(urlparse(next_url).path)
    except Resolver404:
        return False
    return resolved.url_name == 'authorize' and 'oauth2_provider' in resolved.app_names


def resolve_login_method(email: str, next_url: str | None) -> LoginMethod:
    """
    Determine how the user with `email` should authenticate.

    Returns 'password' or the name of a social-auth backend. `next_url` decides
    whether the user needs public site access or admin access.
    """
    email = email.strip().lower()
    if not email:
        raise LoginMethodError('invalid_email', _('Invalid email address'))

    user = User.objects.filter(email__iexact=email, is_active=True).first()
    person = user.get_corresponding_person() if user else None
    if user is None or person is None:
        msg = _('No user found with this email address. Ask your administrator to create an account for you.')
        raise LoginMethodError('no_user', msg)

    if _next_is_public_site(next_url):
        if not user.can_access_public_site(plan=None):
            raise LoginMethodError('no_site_access', _('You do not have access to the public site.'))
    elif not user.can_access_admin(plan=None):
        msg = _(
            'You do not have admin access. Your administrator may need to assign you an action or indicator, or grant '
            'you plan admin status.',
        )
        raise LoginMethodError('no_admin_access', msg)

    # Always use password authentication if the user has a password
    if user.has_usable_password():
        return LoginMethod('password')

    # Use the client's authorization backend
    try:
        client = person.get_admin_client()
    except Exception:
        client = None

    if client is None:
        msg = _('Cannot determine authentication method. The email address domain may be unknown.')
        raise LoginMethodError('no_client', msg)

    if not client.auth_backend:
        raise LoginMethodError('no_password', _('Password authentication is required, but the user has no password.'))

    return LoginMethod(client.auth_backend)
