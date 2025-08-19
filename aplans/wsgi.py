"""
WSGI config for aplans project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.1/howto/deployment/wsgi/
"""
from __future__ import annotations

import os
from datetime import UTC, datetime

from django.core.wsgi import get_wsgi_application

from loguru import logger

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aplans.settings')

django_application = get_wsgi_application()


def run_deployment_checks():
    from django.core import checks
    from django.db import connections

    msgs: list[checks.CheckMessage] = checks.run_checks(include_deployment_checks=True)
    LEVEL_MAP = {
        checks.DEBUG: 'DEBUG',
        checks.INFO: 'INFO',
        checks.WARNING: 'WARNING',
        checks.ERROR: 'ERROR',
        checks.CRITICAL: 'CRITICAL',
    }

    for msg in msgs:
        msg.hint = None
        logger.log(LEVEL_MAP.get(msg.level, 'WARNING'), str(msg))

    # We need to close the connection pool for the database to be available
    # for the worker processes.
    for conn in connections.all():
        conn.close()
        if hasattr(conn, 'close_pool'):
            conn.close_pool()  # type: ignore


# We execute all the checks when running under uWSGI, so that we:
#   - load more of the code to save memory after uWSGI forks workers
#   - keep the state of the system closer to how it is under runserver
try:
    import uwsgi  # type: ignore  # pyright: ignore
    run_deployment_checks()
except ImportError:
    uwsgi = None


def set_log_vars(resp):
    from .log_handler import ISO_FORMAT
    now = datetime.now(UTC)
    uwsgi.set_logvar('isotime', now.strftime(ISO_FORMAT).replace('+00:00', 'Z'))  # type: ignore  # pyright: ignore
    if hasattr(resp, '_response'):
        # Sentry injects a ScopedResponse class
        resp = resp._response
    status = getattr(resp, 'status_code', None)
    level = 'INFO'
    if isinstance(status, int):
        if status >= 400 and status < 500:
            level = 'WARNING'
        elif status >= 500:
            level = 'ERROR'
    uwsgi.set_logvar('level', level)  # type: ignore  # pyright: ignore


def application(env, start_response):
    ret = django_application(env, start_response)
    if uwsgi is not None:
        set_log_vars(ret)
    return ret
