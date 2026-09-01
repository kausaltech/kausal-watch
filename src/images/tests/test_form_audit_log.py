from __future__ import annotations

from io import BytesIO

from django.contrib.contenttypes.models import ContentType
from django.core.files.images import ImageFile
from django.core.files.uploadedfile import SimpleUploadedFile
from wagtail.images.forms import get_image_form

import PIL.Image
import pytest

from audit_logging.models import PlanScopedModelLogEntry
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


def _log_entries_for(image: AplansImage):
    return PlanScopedModelLogEntry.objects.filter(
        content_type=ContentType.objects.get_for_model(AplansImage),
        object_id=str(image.pk),
        action='file.created_or_updated',
    )


class TestAplansImageFormAuditLog:
    def test_multi_upload_pattern_creates_log_entry(self, superuser, plan):
        """
        Regression test for the multi-upload log skip.

        Wagtail's multi-upload AddView calls form.save(commit=False) and then
        saves the instance itself. Before the fix, AplansImageForm.save's
        early-return on commit=False meant log() was never called for these
        creations — so the multi-upload code path produced rows with no
        audit-log entries at all.
        """
        form_class = get_image_form(AplansImage)
        form = form_class(
            data={'title': 'new image', 'collection': plan.root_collection.id},
            files={'file': _png_upload('test.png')},
            user=superuser,
        )
        assert form.is_valid(), form.errors

        image = form.save(commit=False)
        image.uploaded_by_user = superuser
        image.save()

        assert _log_entries_for(image).count() == 1

    def test_standard_form_save_creates_one_log_entry(self, superuser, plan):
        """
        Standard edit path (commit=True).

        Must still produce exactly one log entry — the fix moves logging into a post_save signal handler, so we guard
        against accidental double-logging or no-logging.
        """
        image = AplansImageFactory.create(
            collection=plan.root_collection,
            file=_png_image_file('orig.png'),
        )
        entries_before = _log_entries_for(image).count()

        form_class = get_image_form(AplansImage)
        form = form_class(
            data={'title': 'renamed', 'collection': image.collection_id},
            instance=image,
            user=superuser,
        )
        assert form.is_valid(), form.errors
        form.save()

        assert _log_entries_for(image).count() == entries_before + 1

    def test_direct_save_does_not_log(self, plan):
        """
        Save that bypasses the form.

        A save that bypasses the form (e.g. from a management command, signal,
        or factory) must not emit a file.created_or_updated entry — only form
        saves should.
        """
        image = AplansImageFactory.create(
            collection=plan.root_collection,
            file=_png_image_file('direct.png'),
        )
        entries_before = _log_entries_for(image).count()

        image.title = 'renamed by code'
        image.save()

        assert _log_entries_for(image).count() == entries_before
