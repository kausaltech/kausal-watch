from __future__ import annotations

import os
from typing import cast

from celery import Celery
from celery.signals import setup_logging, worker_process_init, worker_process_shutdown

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'aplans.settings')

app = Celery('aplans')

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')


@worker_process_init.connect(weak=False)
def init_worker_metrics(*args, **kwargs):
    if not os.getenv('OTEL_EXPORTER_OTLP_METRICS_ENDPOINT'):
        return

    from opentelemetry.instrumentation.celery import CeleryInstrumentor
    from opentelemetry.trace import NoOpTracerProvider

    from kausal_common.telemetry.metrics import init_metrics

    init_metrics()
    CeleryInstrumentor().instrument(tracer_provider=NoOpTracerProvider())


@worker_process_shutdown.connect(weak=False)
def shutdown_worker_metrics(*args, **kwargs):
    if not os.getenv('OTEL_EXPORTER_OTLP_METRICS_ENDPOINT'):
        return

    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider

    provider = metrics.get_meter_provider()
    if isinstance(provider, MeterProvider):
        provider.shutdown(timeout_millis=2_500)


@setup_logging.connect
def config_loggers(*args, **kwargs):
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(cast('dict[str, object]', settings.LOGGING))


# Load task modules from all registered Django app configs.
app.autodiscover_tasks()
