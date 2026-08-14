from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError

import pytest

from images.models import AplansImage
from images.tests.factories import AplansImageFactory

pytestmark = pytest.mark.django_db


def test_reports_nothing_when_files_are_intact():
    AplansImageFactory.create()
    out = StringIO()

    call_command('check_media_integrity', stdout=out)

    assert 'No problems found' in out.getvalue()


def test_reports_files_shared_by_several_objects():
    image = AplansImageFactory.create()
    other_image = AplansImageFactory.create()
    AplansImage.objects.filter(pk=other_image.pk).update(file=image.file.name)
    err = StringIO()

    with pytest.raises(CommandError, match='Found 1 problem'):
        call_command('check_media_integrity', stderr=err)

    assert f'file {image.file.name!r} is shared by 2 objects' in err.getvalue()


def test_reports_files_missing_from_storage():
    image = AplansImageFactory.create()
    image.file.storage.delete(image.file.name)
    err = StringIO()

    with pytest.raises(CommandError, match='Found 1 problem'):
        call_command('check_media_integrity', '--include-renditions', stderr=err)

    assert f'AplansImage {image.pk}: file {image.file.name!r} is missing from storage' in err.getvalue()
