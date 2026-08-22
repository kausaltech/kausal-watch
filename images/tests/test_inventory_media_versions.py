from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError

import pytest

from aplans.media_integrity import (
    LOSSLESS,
    MISSING,
    OVERWRITTEN,
    UNKNOWN_HASHES,
    classify_rows,
    content_ever_changed,
)

from images.management.commands.inventory_media_versions import Command
from images.tests.fake_s3 import BUCKET, FakeClient, FakeStorage, sha1_hex

pytestmark = pytest.mark.django_db


def _row(pk: int, file_hash: str = 'abc', file_size: int | None = 10) -> dict:
    return {'pk': pk, 'file_hash': file_hash, 'file_size': file_size}


def test_rows_recording_the_same_hash_are_lossless():
    assert classify_rows([_row(1), _row(2)]) == LOSSLESS


def test_rows_recording_different_hashes_were_overwritten():
    assert classify_rows([_row(1, 'abc'), _row(2, 'def')]) == OVERWRITTEN


def test_blank_hash_is_not_treated_as_a_match():
    """A lazily-populated `file_hash` is unknown, not equal to another row's hash."""
    assert classify_rows([_row(1, ''), _row(2, '')]) == UNKNOWN_HASHES


def test_lossless_groups_need_no_restore_but_still_need_the_bytes_present():
    rows = [_row(1), _row(2)]
    entry = {
        'kind': LOSSLESS,
        'versions': [{'VersionId': 'v1'}],
        'rows': rows,
        'matched': {'1': ['v1'], '2': ['v1']},
        'content_ever_changed': False,
    }

    assert Command().is_recoverable(entry) is True

    assert Command().is_recoverable({**entry, 'versions': []}) is False


def test_missing_file_is_recoverable_only_if_a_version_survives():
    rows = [_row(1, '')]
    base = {'kind': MISSING, 'rows': rows, 'matched': {}, 'content_ever_changed': False}
    assert Command().is_recoverable({**base, 'versions': []}) is False
    assert Command().is_recoverable({**base, 'versions': [{'VersionId': 'v1'}]}) is True


def test_overwritten_group_needs_a_matching_version_for_every_row():
    rows = [_row(1, 'abc'), _row(2, 'def')]
    entry = {
        'kind': OVERWRITTEN,
        'versions': [{'VersionId': 'v1'}],
        'rows': rows,
        'matched': {'1': ['v1'], '2': []},
        'content_ever_changed': True,
    }
    assert Command().is_recoverable(entry) is False

    entry['matched'] = {'1': ['v1'], '2': ['v2']}
    assert Command().is_recoverable(entry) is True


def test_versions_are_matched_on_the_recorded_size_when_hashes_are_not_verified():
    rows = [_row(1, file_size=10), _row(2, file_size=20)]
    versions = [{'VersionId': 'v1', 'Size': 10}, {'VersionId': 'v2', 'Size': 20}]

    matched = Command().match_rows(rows, versions, by='Size')

    assert matched == {'1': ['v1'], '2': ['v2']}


def test_errors_out_on_non_s3_storage():
    """Under pytest the default storage is in-memory, which has no version history to report."""
    with pytest.raises(CommandError, match='not S3-backed'):
        call_command('inventory_media_versions', stdout=StringIO())


def test_equal_etags_prove_the_content_never_changed():
    versions = [{'ETag': 'same'}, {'ETag': 'same'}]

    assert content_ever_changed(versions) is False


def test_differing_etags_mean_the_content_may_have_changed():
    assert content_ever_changed([{'ETag': 'a'}, {'ETag': 'b'}]) is True


def test_group_with_one_content_is_recoverable_even_when_hashes_are_unknown():
    """
    Unknown row hashes plus a single ETag across all versions means nothing was ever overwritten.

    There is no lost content to restore -- the rows only need keys of their own.
    """
    entry = {
        'kind': UNKNOWN_HASHES,
        'versions': [{'VersionId': 'v1'}, {'VersionId': 'v2'}],
        'rows': [_row(1, ''), _row(2, '')],
        'matched': {},
        'content_ever_changed': False,
    }

    assert Command().is_recoverable(entry) is True


def test_group_with_unknown_hashes_and_changed_content_needs_review():
    entry = {
        'kind': UNKNOWN_HASHES,
        'versions': [{'VersionId': 'v1'}, {'VersionId': 'v2'}],
        'rows': [_row(1, ''), _row(2, '')],
        'matched': {'1': [], '2': []},
        'content_ever_changed': True,
    }

    assert Command().is_recoverable(entry) is False


def test_missing_file_needs_a_version_matching_what_the_row_recorded():
    """
    A surviving version is not enough on its own.

    Where a sibling overwrote the key before being deleted, the survivor holds the sibling's bytes.
    """
    rows = [_row(1, 'abc')]
    entry = {
        'kind': MISSING,
        'versions': [{'VersionId': 'v1'}, {'VersionId': 'v2'}],
        'rows': rows,
        'matched': {'1': []},
        'content_ever_changed': True,
    }

    assert Command().is_recoverable(entry) is False

    entry['matched'] = {'1': ['v1']}
    assert Command().is_recoverable(entry) is True


def test_missing_file_with_a_single_content_is_recoverable_by_elimination():
    entry = {
        'kind': MISSING,
        'versions': [{'VersionId': 'v1'}, {'VersionId': 'v2'}],
        'rows': [_row(1, '')],
        'matched': {'1': []},
        'content_ever_changed': False,
    }

    assert Command().is_recoverable(entry) is True


def test_a_single_content_does_not_vouch_for_a_row_that_recorded_a_different_hash():
    """Versioning enabled after an overwrite leaves one ETag holding bytes the row never had."""
    entry = {
        'kind': MISSING,
        'versions': [{'VersionId': 'v1'}],
        'rows': [_row(1, 'abc')],
        'matched': {'1': []},
        'content_ever_changed': False,
    }

    assert Command().is_recoverable(entry) is False


def test_lossless_group_whose_hash_matches_no_surviving_version_is_not_recoverable():
    """
    Versioning can begin after a sibling has already overwritten the key.

    The rows then agree with each other about a hash whose bytes are nowhere in the history, so the
    repair would refuse them -- and the inventory must not promise otherwise.
    """
    rows = [_row(1, 'agreed'), _row(2, 'agreed')]
    entry = {
        'kind': LOSSLESS,
        'versions': [{'VersionId': 'v1'}],
        'rows': rows,
        'matched': {'1': [], '2': []},
        'content_ever_changed': False,
    }

    assert Command().is_recoverable(entry) is False


def test_verify_hashes_reaches_a_version_beneath_a_delete_marker():
    """
    A deleted key has no current version, but the surviving ones are still the row's candidates.

    Skipping them would report a file as needing review that `repair_media_files` can restore.
    """
    own = b'the-rows-own-bytes'
    name = 'original_images/2026-06/gone.png'
    rows = [{'pk': 1, 'file': name, 'file_hash': sha1_hex(own), 'file_size': len(own)}]
    client = FakeClient(name, [own], deleted=True)

    entry = Command().inspect(client, FakeStorage(), BUCKET, name, rows, shared=False, verify_hashes=True)

    assert entry['deleted'] is True
    assert entry['matched']['1'] == ['v0']
    assert entry['recoverable'] is True
