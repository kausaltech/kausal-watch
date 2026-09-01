from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from wagtail.images.forms import BaseImageForm

if TYPE_CHECKING:
    from collections.abc import Iterator

    from django.core.files.storage import Storage
    from django.db.models.fields.files import FieldFile

    from images.models import AplansImage


_FORM_USER_ATTR = '_aplans_image_form_user'


class _OldFileDeleteGuard:
    """
    Storage proxy that suppresses delete() on the path where the replacement upload just landed.

    ``BaseImageForm.save()`` unconditionally calls
    ``self.original_file.storage.delete(self.original_file.name)`` after the
    new upload is written. When ``get_available_name`` returns the original
    path for the replacement — either because the storage has
    ``file_overwrite=True`` (typical for S3), or because the original was
    missing on storage so there was no name conflict — that delete destroys
    the bytes we just wrote. Wrapping the storage with this guard turns that
    one delete into a no-op while leaving deletes targeting any other path
    (the normal rename-to-a-new-path case) intact.
    """

    def __init__(self, wrapped: Storage, instance: AplansImage) -> None:
        self._wrapped = wrapped
        self._instance = instance

    def delete(self, name: str) -> None:
        if name == self._instance.file.name:
            return
        self._wrapped.delete(name)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)


@contextmanager
def _guarded_storage(file_obj: FieldFile, instance: AplansImage) -> Iterator[None]:
    original_storage = file_obj.storage
    file_obj.storage = _OldFileDeleteGuard(original_storage, instance)  # type: ignore[assignment]  # pyright: ignore[reportAttributeAccessIssue]
    try:
        yield
    finally:
        file_obj.storage = original_storage


class AplansImageForm(BaseImageForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.get('user')
        self.user = user
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        # Tag the instance so the post_save signal can log the save regardless
        # of whether commit=True (model saved here) or commit=False (Wagtail's
        # multi-upload AddView saves the model itself afterwards).
        setattr(self.instance, _FORM_USER_ATTR, self.user)

        instance: AplansImage
        if 'file' in self.changed_data and self.original_file:
            with _guarded_storage(self.original_file, self.instance):
                instance = super().save(commit=commit)
        else:
            instance = super().save(commit=commit)

        return instance
