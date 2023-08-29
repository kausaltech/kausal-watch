from __future__ import annotations

import typing
from contextlib import contextmanager
from contextvars import ContextVar


if typing.TYPE_CHECKING:
    from aplans.types import WatchAdminRequest
    from django.db.models import Model


ctx_request: ContextVar[WatchAdminRequest] = ContextVar('request')
ctx_instance: ContextVar[Model] = ContextVar('instance')


@contextmanager
def set_context_var(var: ContextVar, value):
    try:
        var.get()
    except LookupError:
        pass  # expected
    else:
        raise Exception("context variable already set")
    token = var.set(value)
    try:
        yield
    finally:
        var.reset(token)


@contextmanager
def set_request(request: 'WatchRequest'):
    with set_context_var(ctx_request, request):
        yield


@contextmanager
def set_instance(instance: Model):
    with set_context_var(ctx_instance, instance):
        yield
