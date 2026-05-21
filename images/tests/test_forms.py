from __future__ import annotations

from io import BytesIO
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

from django.core.files.uploadedfile import SimpleUploadedFile
from wagtail.images.forms import get_image_form

import PIL.Image
import pytest

from images.forms import _OldFileDeleteGuard
from images.models import AplansImage
from images.tests.factories import AplansImageFactory

if TYPE_CHECKING:
    from django.core.files.storage import Storage


_PIL_FORMAT_BY_EXT = {
    '.png': ('PNG', 'image/png', 'RGBA'),
    '.jpg': ('JPEG', 'image/jpeg', 'RGB'),
    '.jpeg': ('JPEG', 'image/jpeg', 'RGB'),
}


def _make_uploaded_image(filename: str) -> SimpleUploadedFile:
    ext = '.' + filename.rsplit('.', 1)[-1].lower()
    pil_format, content_type, mode = _PIL_FORMAT_BY_EXT.get(ext, ('PNG', 'image/png', 'RGBA'))
    buf = BytesIO()
    PIL.Image.new(mode, (10, 10), 'white').save(buf, pil_format)
    return SimpleUploadedFile(filename, buf.getvalue(), content_type=content_type)


def _build_form_data(image: AplansImage) -> dict[str, Any]:
    return {
        'title': image.title,
        'collection': image.collection.pk,
        'tags': '',
        'focal_point_x': '',
        'focal_point_y': '',
        'focal_point_width': '',
        'focal_point_height': '',
        'image_credit': image.image_credit,
        'alt_text': image.alt_text,
    }


def _force_same_path_on_save(storage: Storage, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Simulate S3-with-file_overwrite=True semantics.

    Default Storage.get_available_name adds a random suffix when the file
    already exists; with file_overwrite=True it returns the requested name
    unchanged, overwriting the existing object in place.
    """

    def _passthrough(name: str, max_length: int | None = None) -> str:
        return name

    monkeypatch.setattr(storage, 'get_available_name', _passthrough)


class TestOldFileDeleteGuard:
    """Unit tests for the storage proxy that protects the just-uploaded file."""

    def test_delete_suppressed_when_name_matches_instance_file(self):
        wrapped = MagicMock()
        instance = MagicMock()
        instance.file.name = 'original_images/2026-04/sample.png'

        guard = _OldFileDeleteGuard(wrapped, instance)
        guard.delete('original_images/2026-04/sample.png')

        wrapped.delete.assert_not_called()

    def test_delete_passthrough_when_name_differs(self):
        wrapped = MagicMock()
        instance = MagicMock()
        instance.file.name = 'original_images/2026-04/new.png'

        guard = _OldFileDeleteGuard(wrapped, instance)
        guard.delete('original_images/2026-04/old.png')

        wrapped.delete.assert_called_once_with('original_images/2026-04/old.png')


@pytest.mark.django_db
class TestAplansImageFormSave:
    """Integration tests for AplansImageForm.save()."""

    def test_resave_with_same_path_keeps_uploaded_file(self, monkeypatch: pytest.MonkeyPatch):
        existing = AplansImageFactory.create()
        original_path = existing.file.name
        storage = existing.file.storage
        assert storage.exists(original_path)

        _force_same_path_on_save(storage, monkeypatch)

        upload_name = original_path.rsplit('/', 1)[-1]
        ImageForm = get_image_form(AplansImage)
        form = ImageForm(
            data=_build_form_data(existing),
            files={'file': _make_uploaded_image(upload_name)},
            instance=existing,
            user=None,
        )

        assert form.is_valid(), form.errors
        instance = form.save()

        assert instance.file.name == original_path
        assert storage.exists(instance.file.name), (
            'Expected the just-uploaded file to still exist on storage; '
            'the unconditional delete in BaseImageForm.save would remove it '
            'without the _OldFileDeleteGuard.'
        )

    def test_resave_with_different_path_still_deletes_old_file(self):
        existing = AplansImageFactory.create()
        original_path = existing.file.name
        storage = existing.file.storage
        assert storage.exists(original_path)

        ImageForm = get_image_form(AplansImage)
        form = ImageForm(
            data=_build_form_data(existing),
            files={'file': _make_uploaded_image('different-name.png')},
            instance=existing,
            user=None,
        )

        assert form.is_valid(), form.errors
        instance = form.save()

        assert instance.file.name != original_path
        assert storage.exists(instance.file.name)
        assert not storage.exists(original_path), (
            'When the upload lands at a new path, the old file must still be '
            'cleaned up — the guard should only suppress same-path deletes.'
        )

    def test_create_without_original_file_works(self):
        # Building a form without an existing image (no original_file) must
        # still work — the save() override guards against original_file being
        # empty.
        from wagtail.models import Collection

        collection = Collection.get_first_root_node()
        assert collection is not None

        ImageForm = get_image_form(AplansImage)
        form = ImageForm(
            data={
                'title': 'Fresh image',
                'collection': collection.pk,
                'tags': '',
                'focal_point_x': '',
                'focal_point_y': '',
                'focal_point_width': '',
                'focal_point_height': '',
                'image_credit': '',
                'alt_text': '',
            },
            files={'file': _make_uploaded_image('fresh.png')},
            user=None,
        )

        assert form.is_valid(), form.errors
        instance = form.save()

        assert instance.pk is not None
        assert instance.file.storage.exists(instance.file.name)
