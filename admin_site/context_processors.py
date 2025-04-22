import json

from django.conf import settings
from django.utils.safestring import mark_safe

import sentry_sdk


def sentry(request):
    if not settings.SENTRY_DSN:
        return {}
    scope = sentry_sdk.get_current_scope()
    return dict(
        sentry_dsn=settings.SENTRY_DSN, deployment_type=settings.DEPLOYMENT_TYPE,
        sentry_trace_meta=mark_safe(scope.trace_propagation_meta),  # noqa: S308
        sentry_release=scope.get_client().options.get('release'),
    )


def i18n(request):
    return dict(
        language_fallbacks_json=json.dumps(settings.MODELTRANS_FALLBACK),
        supported_languages_json=json.dumps([x[0] for x in settings.LANGUAGES]),
    )
