import json
from django.conf import settings
from django.utils.safestring import mark_safe
from sentry_sdk import Hub


def sentry(request):
    hub: Hub = Hub.current
    if not settings.SENTRY_DSN:
        return {}
    return dict(
        sentry_dsn=settings.SENTRY_DSN, deployment_type=settings.DEPLOYMENT_TYPE,
        sentry_trace_meta=mark_safe(hub.trace_propagation_meta()),
        sentry_release=hub.client.options.get('release'),
    )


def i18n(request):
    return dict(
        language_fallbacks_json=json.dumps(settings.MODELTRANS_FALLBACK),
        supported_languages_json=json.dumps([x[0] for x in settings.LANGUAGES]),
    )
