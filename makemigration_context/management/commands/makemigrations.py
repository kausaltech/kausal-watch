from contextlib import contextmanager

from django.core.management.commands import makemigrations


_makemigrations_in_progress = False


@contextmanager
def make_migrations_context(status: bool):
    global _makemigrations_in_progress
    _makemigrations_in_progress = status
    yield
    _makemigrations_in_progress = not status


def running_under_makemigrations():
    global _makemigrations_in_progress
    return _makemigrations_in_progress


class Command(makemigrations.Command):
    def handle(self, *args, **kwargs):
        with make_migrations_context(True):
            super(Command, self).handle(*args, **kwargs)
