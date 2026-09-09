from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def _pin_email_dns_name() -> None:
    """
    Give Django's email machinery a fixed FQDN for the run.

    Every outgoing message gets a `Message-ID` built from `DNS_NAME`, which resolves the
    local FQDN through `socket.getfqdn()` — a reverse DNS lookup. The result is cached for
    the process, so the cost lands once, on whichever test happens to send mail first. On a
    machine whose hostname only resolves over mDNS that single lookup blocks for around two
    minutes, which is a third of the suite; it silently looks like a hung test.
    """
    from django.core.mail import utils as mail_utils

    mail_utils.DNS_NAME._fqdn = 'example.com'


def pytest_sessionstart(session: pytest.Session) -> None:
    """Register Watch fixtures after pytest-django has initialized Django."""
    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()

    _pin_email_dns_name()

    config = session.config
    plugin_name = 'aplans.pytest_fixtures'
    if config.pluginmanager.hasplugin(plugin_name):
        return

    from aplans import pytest_fixtures

    config.pluginmanager.register(pytest_fixtures, plugin_name)
