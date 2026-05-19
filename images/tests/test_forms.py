from __future__ import annotations

from io import BytesIO

from django.core.files.images import ImageFile
from django.core.files.uploadedfile import SimpleUploadedFile
from wagtail.images.forms import get_image_form

import PIL.Image
import pytest

from images.models import AplansImage
from images.tests.factories import AplansImageFactory

pytestmark = pytest.mark.django_db


def _png_bytes() -> bytes:
    buf = BytesIO()
    PIL.Image.new('RGBA', (8, 8), 'white').save(buf, 'PNG')
    return buf.getvalue()


def _png_upload(filename: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(filename, _png_bytes(), content_type='image/png')


def _png_image_file(filename: str) -> ImageFile:
    return ImageFile(BytesIO(_png_bytes()), name=filename)


class TestAplansImageFormSelfDeleteTrap:
    def test_save_preserves_new_file_when_original_was_missing(self, plan_admin_user, plan):
        """
        Regression test for the self-delete trap.

        When the original file is missing on storage at the time of re-upload
        and the new upload uses the same basename, storage.get_available_name
        will reuse the original path. BaseImageForm.save's commit branch would
        then delete what was just uploaded. AplansImageForm.save must prevent
        this.
        """
        image = AplansImageFactory.create(
            collection=plan.root_collection,
            file=_png_image_file('ace34991.png'),
        )
        storage = image.file.storage
        original_path = image.file.name
        assert storage.exists(original_path)

        # Simulate external deletion of the original file.
        storage.delete(original_path)
        assert not storage.exists(original_path)

        # Re-upload using the same basename. get_available_name reuses the path
        # because the original is missing — so without the fix, BaseImageForm
        # would delete the file it just uploaded.
        basename = original_path.rsplit('/', 1)[-1]
        form_class = get_image_form(AplansImage)
        form = form_class(
            data={'title': image.title, 'collection': image.collection_id},
            files={'file': _png_upload(basename)},
            instance=image,
            user=plan_admin_user,
        )
        assert form.is_valid(), form.errors
        saved = form.save()

        assert storage.exists(saved.file.name), (
            'AplansImageForm.save deleted the file it just uploaded'
        )

    def test_save_deletes_old_file_when_path_changes(self, plan_admin_user, plan):
        """
        Normal-path behaviour.

        When re-uploading a differently-named file, the old file is deleted
        and the new file remains. The fix must not regress this.
        """

        image = AplansImageFactory.create(
            collection=plan.root_collection,
            file=_png_image_file('ace34991.png'),
        )
        storage = image.file.storage
        original_path = image.file.name
        assert storage.exists(original_path)

        form_class = get_image_form(AplansImage)
        form = form_class(
            data={'title': image.title, 'collection': image.collection_id},
            files={'file': _png_upload('different-name.png')},
            instance=image,
            user=plan_admin_user,
        )
        assert form.is_valid(), form.errors
        saved = form.save()

        assert saved.file.name != original_path
        assert storage.exists(saved.file.name)
        assert not storage.exists(original_path)
