from __future__ import annotations

from functools import wraps
from importlib import import_module
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models.signals import post_delete
from wagtail.tasks import delete_file_from_storage_task

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import ModuleType

    from django.db.models import Model

logger = logger.bind(name='aplans.media_cleanup')

_DISPATCH_UID = 'aplans_guarded_file_cleanup'

_wrapped_modules: set[str] = set()


def file_name_is_in_use(model: type[Model], name: str) -> bool:
    """Return whether any row of `model` still references `name` as its file."""
    return model._default_manager.filter(file=name).exists()


def guarded_post_delete_file_cleanup(sender: type[Model], instance: Any, **_kwargs: Any) -> None:
    """
    Delete the file of a just-deleted media object, unless another object still points at it.

    This replaces Wagtail's `post_delete_file_cleanup`, which deletes unconditionally. Storage
    backends configured with `file_overwrite=True` (the django-storages S3 default) hand out the
    requested path even when it is taken, so two uploads of the same filename end up sharing a
    single object. Deleting either row would then destroy the other row's file, which is how
    images have been losing their originals in production.

    The flow that kept triggering it is Wagtail's duplicate detection in the image chooser:
    uploading a file that already exists writes over the existing object (same filename, same
    upload directory, no de-duplication), Wagtail then notices the contents match and offers to
    reuse the existing image, and confirming that deletes the row just created -- along with the
    file both rows point at.
    """
    name: str = instance.file.name
    if not name:
        return
    pk = instance.pk
    storage = instance.file.storage

    def delete_file() -> None:
        if file_name_is_in_use(sender, name):
            logger.warning(f'Not deleting file {name!r} of deleted {sender.__name__} {pk}: another object still references it')
            return
        logger.info(f'Deleting file {name!r} of deleted {sender.__name__} {pk}')
        delete_file_from_storage_task.enqueue(storage.deconstruct(), name)

    transaction.on_commit(delete_file)


def install_file_cleanup_guard() -> None:
    """Replace Wagtail's unconditional file-cleanup receivers with `guarded_post_delete_file_cleanup`."""
    from wagtail.documents.signal_handlers import post_delete_file_cleanup as wagtail_document_cleanup
    from wagtail.images.signal_handlers import post_delete_file_cleanup as wagtail_image_cleanup

    from documents.models import AplansDocument
    from images.models import AplansImage, AplansRendition

    for model, wagtail_receiver in (
        (AplansImage, wagtail_image_cleanup),
        (AplansRendition, wagtail_image_cleanup),
        (AplansDocument, wagtail_document_cleanup),
    ):
        post_delete.disconnect(wagtail_receiver, sender=model)
        post_delete.connect(guarded_post_delete_file_cleanup, sender=model, dispatch_uid=_DISPATCH_UID)


def ensure_file_cleanup_guard_installed() -> None:
    """
    Install the guard now, and again after Wagtail connects its own signal handlers.

    `images` and `documents` are listed before `wagtail.images` and `wagtail.documents` in
    INSTALLED_APPS, so their `ready()` runs first: at that point Wagtail's receivers are not
    connected yet and disconnecting them would silently do nothing. Wrapping
    `register_signal_handlers` makes the guard survive either app ordering.
    """
    install_file_cleanup_guard()
    for module_name in ('wagtail.images.signal_handlers', 'wagtail.documents.signal_handlers'):
        _wrap_register_signal_handlers(import_module(module_name))


def _wrap_register_signal_handlers(module: ModuleType) -> None:
    if module.__name__ in _wrapped_modules:
        return
    original: Callable[[], None] = module.register_signal_handlers

    @wraps(original)
    def register_signal_handlers() -> None:
        original()
        install_file_cleanup_guard()

    module.register_signal_handlers = register_signal_handlers  # pyright: ignore[reportAttributeAccessIssue]
    _wrapped_modules.add(module.__name__)
