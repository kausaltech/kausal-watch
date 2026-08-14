from __future__ import annotations

from unittest.mock import patch

from django.db.models.signals import post_delete
from wagtail.documents.signal_handlers import post_delete_file_cleanup as wagtail_document_file_cleanup
from wagtail.images.signal_handlers import post_delete_file_cleanup as wagtail_image_file_cleanup

import pytest

from documents.models import AplansDocument
from documents.tests.factories import AplansDocumentFactory
from images.models import AplansImage, AplansRendition
from images.tests.factories import AplansImageFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ('model', 'wagtail_receiver'),
    [
        (AplansImage, wagtail_image_file_cleanup),
        (AplansRendition, wagtail_image_file_cleanup),
        (AplansDocument, wagtail_document_file_cleanup),
    ],
)
def test_wagtail_unconditional_cleanup_is_not_connected(model, wagtail_receiver):
    """
    Wagtail's own receiver must be gone, not merely shadowed by ours.

    It deletes the file whatever else points at it, so leaving it connected would defeat the guard.
    Wagtail connects it in its own app config, which runs after ours, so this also covers the
    re-installation that `ensure_file_cleanup_guard_installed` does afterwards.
    """
    assert post_delete.disconnect(wagtail_receiver, sender=model) is False


def test_deleting_image_deletes_its_file(django_capture_on_commit_callbacks):
    image = AplansImageFactory.create()
    file_name = image.file.name

    with (
        patch('aplans.media_cleanup.delete_file_from_storage_task') as task,
        django_capture_on_commit_callbacks(execute=True),
    ):
        image.delete()

    task.enqueue.assert_called_once()
    assert task.enqueue.call_args.args[1] == file_name


def test_deleting_image_keeps_file_that_another_image_still_uses(django_capture_on_commit_callbacks):
    image = AplansImageFactory.create()
    other_image = AplansImageFactory.create()
    # Storages with file_overwrite=True (the django-storages S3 default) hand out a path that is
    # already taken, which is how two images end up sharing one file in production.
    AplansImage.objects.filter(pk=other_image.pk).update(file=image.file.name)

    with (
        patch('aplans.media_cleanup.delete_file_from_storage_task') as task,
        django_capture_on_commit_callbacks(execute=True),
    ):
        image.delete()

    task.enqueue.assert_not_called()


def test_deleting_document_keeps_file_that_another_document_still_uses(django_capture_on_commit_callbacks):
    document = AplansDocumentFactory.create()
    other_document = AplansDocumentFactory.create()
    AplansDocument.objects.filter(pk=other_document.pk).update(file=document.file.name)

    with (
        patch('aplans.media_cleanup.delete_file_from_storage_task') as task,
        django_capture_on_commit_callbacks(execute=True),
    ):
        document.delete()

    task.enqueue.assert_not_called()
