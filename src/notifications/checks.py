from __future__ import annotations

from django.conf import settings
from django.core.checks import Error

from .utils import is_valid_public_domain_url


def check_admin_base_url(app_configs, **kwargs) -> list[Error]:
    """
    Ensure ``ADMIN_BASE_URL`` is a public URL outside of development.

    Notification emails embed admin edit links derived from ``ADMIN_BASE_URL``.
    A localhost or private-network value would render unusable links, so we fail
    fast at startup rather than at send time.
    """
    if settings.DEPLOYMENT_TYPE == 'development':
        return []
    if is_valid_public_domain_url(settings.ADMIN_BASE_URL):
        return []
    return [
        Error(
            f'ADMIN_BASE_URL is not a public URL: {settings.ADMIN_BASE_URL}',
            hint='Set ADMIN_BASE_URL to a publicly reachable https URL so notification admin links work.',
            id='notifications.E001',
        )
    ]
