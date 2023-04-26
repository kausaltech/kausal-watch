from contextlib import contextmanager
from contextvars import ContextVar

ctx_request = ContextVar('request')
ctx_instance = ContextVar('instance')


@contextmanager
def set_context_var(var, value):
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
def set_request(request):
    with set_context_var(ctx_request, request):
        yield


@contextmanager
def set_instance(instance):
    with set_context_var(ctx_instance, instance):
        yield
