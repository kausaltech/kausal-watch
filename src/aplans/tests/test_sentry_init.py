from __future__ import annotations

import sentry_sdk


def test_sentry_is_not_initialised_for_tests() -> None:
    """
    Test runs must not report to Sentry, whether or not a DSN happens to be configured.

    See the comment next to the init_sentry() call in the settings module.
    """
    assert not sentry_sdk.get_client().is_active()


def test_no_sentry_integrations_instrument_the_test_run() -> None:
    """
    An inactive client is not enough: the integrations are what cost time.

    They patch the database driver and open a span per query, which stays expensive
    even when the events are then dropped for want of a DSN.
    """
    assert not getattr(sentry_sdk.get_client(), 'integrations', None)
