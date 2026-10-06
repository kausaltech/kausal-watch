from __future__ import annotations

from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error

from .utils import is_valid_public_domain_url


def check_admin_base_url(app_configs, **kwargs) -> list[Error]:
    """
    Ensure ``ADMIN_BASE_URL`` is a public https URL outside of development.

    Notification emails embed admin edit links derived from ``ADMIN_BASE_URL``.
    A localhost or private-network value would render unusable links, so we fail
    fast at startup rather than at send time. Some of those links carry one-time
    credentials (access-request password links), so plaintext http is rejected too.
    """
    if settings.DEPLOYMENT_TYPE == 'development':
        return []
    url = settings.ADMIN_BASE_URL
    if urlparse(url).scheme == 'https' and is_valid_public_domain_url(url):
        return []
    return [
        Error(
            f'ADMIN_BASE_URL is not a public https URL: {url}',
            hint='Set ADMIN_BASE_URL to a publicly reachable https URL so notification admin links work.',
            id='notifications.E001',
        )
    ]
