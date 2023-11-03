"""
WSGI config for aplans project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/2.1/howto/deployment/wsgi/
"""

import os
from loguru import logger

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aplans.settings')

application = get_wsgi_application()

def run_deployment_checks():
    from django.core import checks  # noqa

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

# We execute all the checks when running under uWSGI, so that we:
#   - load more of the code to save memory after uWSGI forks workers
#   - keep the state of the system closer to how it is under runserver
try:
    import uwsgi  # type: ignore  # noqa
    run_deployment_checks()
except ImportError:
    pass
