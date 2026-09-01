from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest


def pytest_sessionstart(session: pytest.Session) -> None:
    """Register Watch fixtures after pytest-django has initialized Django."""
    import django
    from django.apps import apps

    if not apps.ready:
        django.setup()

    config = session.config
    plugin_name = 'aplans.pytest_fixtures'
    if config.pluginmanager.hasplugin(plugin_name):
        return

    from aplans import pytest_fixtures

    config.pluginmanager.register(pytest_fixtures, plugin_name)
