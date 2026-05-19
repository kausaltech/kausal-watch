from __future__ import annotations

from typing import TYPE_CHECKING, Any

from wagtail.images.forms import BaseImageForm
from wagtail.log_actions import log

if TYPE_CHECKING:
    from django.core.files.storage import Storage

    from images.models import AplansImage


class _OldFileDeleteGuard:
    """
    Storage proxy that suppresses delete() when the targeted path matches the form instance's current file path.

    Used to neutralise BaseImageForm.save's commit branch, which unconditionally
    deletes the original file from storage after upload. If storage.get_available_name
    reused the original path for the new upload (because the original was missing
    on storage), that delete destroys the just-uploaded file.
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


class AplansImageForm(BaseImageForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.get('user')
        self.user = user
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        original_file = self.original_file
        if original_file is None:
            instance: AplansImage = super().save(commit=commit)
        else:
            unwrapped_storage = original_file.storage
            original_file.storage = _OldFileDeleteGuard(unwrapped_storage, self.instance)
            try:
                instance = super().save(commit=commit)
            finally:
                original_file.storage = unwrapped_storage

        if commit is False:
            return instance

        log(
            instance=instance,
            action='file.created_or_updated',
            user=self.user,
        )
        return instance
