from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from django.core.management import call_command
from django.core.management.base import CommandError

import pytest

from actions.tests.factories import PlanFactory
from images.models import AplansImage
from images.tests.factories import AplansImageFactory

if TYPE_CHECKING:
    from pathlib import Path

    from wagtail.models import Collection

pytestmark = pytest.mark.django_db

HASH_A = 'a' * 40
HASH_B = 'b' * 40


def _shared_images(*hashes: str, collection: Collection | None = None, sizes: list[int] | None = None) -> str:
    """Point one image per hash at a single key, and return that key."""
    images = [AplansImageFactory.create() for _ in hashes]
    name = images[0].file.name
    pks = sorted(image.pk for image in images)
    AplansImage.objects.filter(pk__in=pks).update(file=name)
    if collection is not None:
        AplansImage.objects.filter(pk__in=pks).update(collection=collection)
    for pk, file_hash, size in zip(pks, hashes, sizes or [10] * len(hashes), strict=True):
        AplansImage.objects.filter(pk=pk).update(file_hash=file_hash, file_size=size)
    return name


def _triage(*args: str) -> str:
    out = StringIO()
    call_command('triage_shared_media', *args, stdout=out)
    return out.getvalue()


def test_ignores_keys_with_only_one_row():
    AplansImageFactory.create()

    assert 'SAME' not in _triage()
    assert 'DIFFER' not in _triage()


def test_reports_rows_that_agree_as_same():
    name = _shared_images(HASH_A, HASH_A)

    output = _triage()

    assert f'SAME     2x {name}' in output
    assert "'SAME': 1" in output


def test_reports_rows_that_disagree_as_differ():
    name = _shared_images(HASH_A, HASH_B)

    output = _triage()

    assert f'DIFFER   2x {name}' in output
    assert "'DIFFER': 1" in output


def test_reports_agreeing_hashes_with_differing_sizes_as_differ():
    """A hash and a size that contradict each other are not evidence that nothing was lost."""
    _shared_images(HASH_A, HASH_A, sizes=[10, 20])

    assert "'DIFFER': 1" in _triage()


def test_treats_a_blank_hash_as_unknown_rather_than_as_a_match():
    """`file_hash` is populated lazily, so two blanks must not be read as "the same content"."""
    _shared_images('', '')

    output = _triage()

    assert "'UNKNOWN': 1" in output
    assert 'SAME' not in output


def test_attributes_rows_to_the_plan_owning_their_collection():
    plan = PlanFactory.create()
    assert plan.root_collection is not None
    _shared_images(HASH_A, HASH_A, collection=plan.root_collection)

    assert plan.identifier in _triage()


def test_counts_a_group_owned_by_no_plan_as_residue():
    _shared_images(HASH_A, HASH_A)

    output = _triage()

    assert 'NO-PLAN' in output
    assert "'residue': 1" in output


def test_emits_one_key_file_per_verdict(tmp_path: Path):
    same = _shared_images(HASH_A, HASH_A)
    differ = _shared_images(HASH_A, HASH_B)

    _triage('--emit-keys', str(tmp_path))

    assert (tmp_path / 'same-keys.txt').read_text() == f'{same}\n'
    assert (tmp_path / 'differ-keys.txt').read_text() == f'{differ}\n'
    assert (tmp_path / 'unknown-keys.txt').read_text() == ''


def test_emptied_key_file_replaces_a_previous_run_s_findings(tmp_path: Path):
    """
    A verdict with no findings must truncate its file, not leave the last run's behind.

    These files are fed straight to `repair_media_files --keys-file`, so a leftover would name keys
    that have since been repaired.
    """
    stale = tmp_path / 'differ-keys.txt'
    stale.write_text('documents/already-repaired.pdf\n')
    _shared_images(HASH_A, HASH_A)

    _triage('--emit-keys', str(tmp_path))

    assert stale.read_text() == ''


def test_removes_the_missing_key_file_when_missing_was_not_examined(tmp_path: Path):
    """Writing it empty would assert that nothing is missing when the question was never asked."""
    stale = tmp_path / 'missing-keys.txt'
    stale.write_text('original_images/2026-01/gone.jpg\n')

    output = _triage('--emit-keys', str(tmp_path))

    assert not stale.exists()
    assert 'not determined by this run' in output


def test_emits_the_missing_key_file_when_asked(tmp_path: Path):
    image = AplansImageFactory.create()
    image.file.storage.delete(image.file.name)

    _triage('--include-missing', '--emit-keys', str(tmp_path))

    assert (tmp_path / 'missing-keys.txt').read_text() == f'{image.file.name}\n'


def test_refuses_to_emit_keys_to_a_path_that_is_not_a_directory(tmp_path: Path):
    with pytest.raises(CommandError, match='is not a directory'):
        _triage('--emit-keys', str(tmp_path / 'nope'))


def test_reports_missing_rows_when_asked():
    image = AplansImageFactory.create()
    image.file.storage.delete(image.file.name)

    output = _triage('--include-missing')

    assert f'MISSING  {image.file.name}' in output
    assert "'MISSING': 1" in output
