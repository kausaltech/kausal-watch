from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django.core.management.base import CommandError

import pytest

from aplans.media_integrity import current_version, is_currently_deleted, list_versions

from images.management.commands.repair_media_files import Command, UnresolvedError
from images.models import AplansImage
from images.tests.factories import AplansImageFactory
from images.tests.fake_s3 import BUCKET, FakeClient, FakeStorage, moved, sha1_hex

if TYPE_CHECKING:
    from django.db.models import FileField

pytestmark = pytest.mark.django_db

FILE_FIELD = cast('FileField', AplansImage._meta.get_field('file'))


def _shared_images(count: int, *, content: bytes = b'same', hashes: list[str] | None = None) -> list[dict[str, Any]]:
    """Create `count` images sharing one key, recording the hash of `content` unless told otherwise."""
    images = [AplansImageFactory.create() for _ in range(count)]
    pks = [image.pk for image in images]
    name = images[0].file.name
    AplansImage.objects.filter(pk__in=pks).update(file=name, file_hash=sha1_hex(content), file_size=len(content))
    if hashes is not None:
        for pk, file_hash in zip(sorted(pks), hashes, strict=True):
            AplansImage.objects.filter(pk=pk).update(file_hash=file_hash)
    return _rows(pks)


def _rows(pks: list[int]) -> list[dict[str, Any]]:
    rows = AplansImage.objects.filter(pk__in=pks).order_by('pk').values('pk', 'file', 'file_hash', 'file_size')
    return [cast('dict[str, Any]', row) for row in rows]


def _command(*, execute: bool = True) -> Command:
    command = Command()
    command.execute_repairs = execute
    return command


def _unshare(
    client: FakeClient, rows: list[dict[str, Any]], storage: FakeStorage | None = None, *, execute: bool = True
) -> tuple[int, int]:
    name = rows[0]['file']
    # By default the shared key is live, so storage reports it as occupied.
    storage = storage if storage is not None else FakeStorage(present={name})
    return _command(execute=execute).unshare(AplansImage, client, storage, FILE_FIELD, BUCKET, name, rows)


def test_identical_content_keeps_the_oldest_row_and_moves_the_rest():
    rows = _shared_images(3)
    name = rows[0]['file']
    client = FakeClient(name, [b'same', b'same'])

    assert _unshare(client, rows) == (2, 0)

    assert AplansImage.objects.get(pk=rows[0]['pk']).file.name == name
    assert AplansImage.objects.get(pk=rows[1]['pk']).file.name == moved(name, 1)
    assert AplansImage.objects.get(pk=rows[2]['pk']).file.name == moved(name, 2)
    assert len(client.copies) == 2
    assert {c['CopySource']['VersionId'] for c in client.copies} == {'v1'}
    assert {c['ACL'] for c in client.copies} == {'public-read'}


def test_dry_run_writes_nothing():
    rows = _shared_images(2)
    name = rows[0]['file']
    client = FakeClient(name, [b'same', b'same'])

    _unshare(client, rows, execute=False)

    assert client.copies == []
    assert AplansImage.objects.get(pk=rows[1]['pk']).file.name == name


def test_overwritten_content_restores_each_row_from_its_own_version():
    old, new = b'old-content', b'new'
    rows = _shared_images(2, hashes=[sha1_hex(old), sha1_hex(new)])
    client = FakeClient(rows[0]['file'], [old, new])

    assert _unshare(client, rows) == (1, 0)

    # The row matching the current bytes keeps the key; the overwritten one is restored elsewhere.
    assert AplansImage.objects.get(pk=rows[1]['pk']).file.name == rows[0]['file']
    assert AplansImage.objects.get(pk=rows[0]['pk']).file.name == moved(rows[0]['file'], 1)
    assert client.copies[0]['CopySource']['VersionId'] == 'v0'


def test_group_is_left_alone_when_no_row_matches_the_current_content():
    rows = _shared_images(2, hashes=['aaa', 'bbb'])
    name = rows[0]['file']
    client = FakeClient(name, [b'one', b'two'])

    assert _unshare(client, rows) == (0, 2)

    assert client.copies == []
    assert AplansImage.objects.get(pk=rows[0]['pk']).file.name == name


def test_group_with_unknown_hashes_and_changed_content_is_all_or_nothing():
    """A blank file_hash cannot be traced to a version, so no row in the group may be moved."""
    rows = _shared_images(3, hashes=['', sha1_hex(b'two'), ''])
    name = rows[0]['file']
    client = FakeClient(name, [b'one', b'two'])

    assert _unshare(client, rows) == (0, 3)

    assert client.copies == []
    assert [AplansImage.objects.get(pk=row['pk']).file.name for row in rows] == [name] * 3


def test_plan_group_refuses_a_row_it_cannot_trace():
    client = FakeClient('k', [b'abc', b'xyz'])
    versions, _markers = list_versions(client, BUCKET, 'k')

    with pytest.raises(UnresolvedError, match='cannot be traced'):
        _command().plan_group(client, BUCKET, 'k', versions, [{'pk': 1, 'file_hash': 'nope'}], deleted=False)


def test_shared_key_that_is_currently_deleted_restores_the_keeper_too():
    rows = _shared_images(2)
    name = rows[0]['file']
    client = FakeClient(name, [b'same'], deleted=True)

    assert _unshare(client, rows, FakeStorage()) == (2, 0)

    # One copy puts the keeper's content back on the shared key, the other moves the second row.
    onto_key = [c for c in client.copies if c['Key'] == name]
    moved_copies = [c for c in client.copies if c['Key'] == moved(name, 1)]
    assert len(onto_key) == 1
    assert len(moved_copies) == 1
    assert AplansImage.objects.get(pk=rows[1]['pk']).file.name == moved(name, 1)


def test_current_version_uses_is_latest_when_timestamps_tie():
    """Second-granularity timestamps cannot order uploads made within the same second."""
    client = FakeClient('k', [b'old', b'new'], same_timestamp=True, api_order='newest_first')

    versions, _markers = list_versions(client, BUCKET, 'k')

    assert versions[-1]['VersionId'] == 'v0'  # recency order is useless here
    current = current_version(versions)
    assert current is not None
    assert current['VersionId'] == 'v1'


def test_keeper_is_chosen_by_is_latest_not_by_timestamp_order():
    old, new = b'old', b'new'
    rows = _shared_images(2, hashes=[sha1_hex(old), sha1_hex(new)])
    name = rows[0]['file']
    client = FakeClient(name, [old, new], same_timestamp=True, api_order='newest_first')

    assert _unshare(client, rows) == (1, 0)

    assert AplansImage.objects.get(pk=rows[1]['pk']).file.name == name
    assert client.copies[0]['CopySource']['VersionId'] == 'v0'


def test_missing_file_is_restored_from_the_version_it_recorded():
    own = b'gone'
    image = AplansImageFactory.create()
    AplansImage.objects.filter(pk=image.pk).update(file_hash=sha1_hex(own))
    rows = _rows([image.pk])
    name = rows[0]['file']
    client = FakeClient(name, [own], deleted=True)

    assert _command().restore_missing(client, FakeStorage(), BUCKET, name, rows) == (1, 0)

    assert client.copies[0]['CopySource'] == {'Bucket': BUCKET, 'Key': name, 'VersionId': 'v0'}
    assert client.copies[0]['Key'] == name


def test_missing_file_restores_its_own_version_not_the_newest():
    """
    A sibling overwrote this key and was then deleted, leaving the row missing.

    The newest surviving version holds the sibling's bytes, so restoring by recency would hand the
    row a file that was never its own.
    """
    own, sibling = b'my-content', b'sibling-content'
    image = AplansImageFactory.create()
    AplansImage.objects.filter(pk=image.pk).update(file_hash=sha1_hex(own))
    rows = _rows([image.pk])
    name = rows[0]['file']
    client = FakeClient(name, [own, sibling], deleted=True)

    assert _command().restore_missing(client, FakeStorage(), BUCKET, name, rows) == (1, 0)

    assert client.copies[0]['CopySource']['VersionId'] == 'v0'


def test_missing_file_with_no_matching_version_is_left_for_review():
    image = AplansImageFactory.create()
    AplansImage.objects.filter(pk=image.pk).update(file_hash='not-in-storage')
    rows = _rows([image.pk])
    name = rows[0]['file']
    client = FakeClient(name, [b'one', b'two'], deleted=True)

    assert _command().restore_missing(client, FakeStorage(), BUCKET, name, rows) == (0, 1)

    assert client.copies == []


def test_missing_file_without_versions_is_reported_not_repaired():
    image = AplansImageFactory.create()
    rows = _rows([image.pk])
    name = rows[0]['file']
    client = FakeClient(name, [], deleted=True)

    assert _command().restore_missing(client, FakeStorage(), BUCKET, name, rows) == (0, 1)

    assert client.copies == []


def test_a_stale_delete_marker_does_not_trigger_a_restore():
    """The key is present; an older delete marker further down the history is not a deletion."""
    image = AplansImageFactory.create()
    rows = _rows([image.pk])
    name = rows[0]['file']
    client = FakeClient(name, [b'here'], stale_marker=True)
    versions, markers = list_versions(client, BUCKET, name)
    assert is_currently_deleted(versions, markers) is False

    assert _command().restore_missing(client, FakeStorage(), BUCKET, name, rows) == (0, 0)

    assert client.copies == []


def test_dry_run_previews_a_deleted_shared_key_instead_of_aborting():
    """
    A key with a delete marker on top reads as free, so allocation cannot ask storage about it.

    On a dry run the keeper's content has not been restored yet, so nothing occupies the key and a
    naive `get_available_name` hands back the very name the row is being moved off — aborting the
    preview for exactly the groups this command exists to fix.
    """
    rows = _shared_images(2)
    name = rows[0]['file']
    client = FakeClient(name, [b'same'], deleted=True)

    assert _unshare(client, rows, FakeStorage(), execute=False) == (2, 0)

    assert client.copies == []
    assert [AplansImage.objects.get(pk=row['pk']).file.name for row in rows] == [name] * 2


def test_allocation_never_hands_out_the_same_name_twice_in_one_run():
    """A dry run writes nothing, so storage cannot report what this run has already allocated."""
    name = 'documents/report.pdf'
    storage = FakeStorage()
    taken = {name}

    first = Command().allocate_key(storage, FILE_FIELD, name, taken)
    second = Command().allocate_key(storage, FILE_FIELD, name, taken)

    assert first != name
    assert second != name
    assert first != second


def test_allocation_gives_up_on_a_storage_that_will_not_de_duplicate():
    class CollapsingStorage(FakeStorage):
        """Ignores the name it is asked about and always hands back the one it already has."""

        def get_available_name(self, name: str, max_length: int | None = None) -> str:
            return 'documents/report.pdf'

    with pytest.raises(CommandError, match='Could not allocate a key distinct'):
        Command().allocate_key(CollapsingStorage(), FILE_FIELD, 'documents/report.pdf', set())


def test_blank_hash_rows_resolve_when_differing_etags_hide_identical_bytes():
    """
    A multipart ETag is not a digest of the content.

    Identical bytes stored with different part sizes carry different ETags — readily produced when
    one version was uploaded and another made by a server-side copy. Reading that as an overwrite
    would strand a group that is entirely recoverable.
    """
    rows = _shared_images(2, hashes=['', ''])
    name = rows[0]['file']
    client = FakeClient(name, [b'same', b'same'], multipart=True)

    assert _unshare(client, rows) == (1, 0)

    assert AplansImage.objects.get(pk=rows[0]['pk']).file.name == name
    assert AplansImage.objects.get(pk=rows[1]['pk']).file.name == moved(name, 1)


def test_blank_hash_rows_are_still_rejected_when_the_bytes_really_differ():
    rows = _shared_images(2, hashes=['', ''])
    name = rows[0]['file']
    client = FakeClient(name, [b'one', b'two'], multipart=True)

    assert _unshare(client, rows) == (0, 2)

    assert client.copies == []
    assert [AplansImage.objects.get(pk=row['pk']).file.name for row in rows] == [name] * 2


def test_a_failed_copy_leaves_the_whole_group_in_the_database_untouched():
    """
    All-or-nothing has to survive execution, not just planning.

    With three rows, a storage failure on a later copy must not leave the earlier siblings already
    repointed at their new keys.
    """
    rows = _shared_images(3)
    name = rows[0]['file']

    class FlakyClient(FakeClient):
        def copy_object(self, **kwargs) -> dict:
            if self.copies:
                raise RuntimeError('S3 is having a moment')
            return super().copy_object(**kwargs)

    client = FlakyClient(name, [b'same', b'same'])

    with pytest.raises(RuntimeError, match='having a moment'):
        _unshare(client, rows)

    assert [AplansImage.objects.get(pk=row['pk']).file.name for row in rows] == [name] * 3


def test_a_failed_sibling_copy_does_not_bring_a_deleted_shared_key_back():
    """
    Restoring the shared key while other rows still point at it would serve them the keeper's bytes.

    That is worse than the 404 they had, so the restore goes last and a sibling failure must leave
    the key deleted.
    """
    rows = _shared_images(2)
    name = rows[0]['file']

    class FlakyClient(FakeClient):
        def copy_object(self, **kwargs) -> dict:
            if kwargs['Key'] != name:  # the sibling's copy
                raise RuntimeError('S3 is having a moment')
            return super().copy_object(**kwargs)

    client = FlakyClient(name, [b'same'], deleted=True)

    with pytest.raises(RuntimeError, match='having a moment'):
        _unshare(client, rows, FakeStorage())

    assert client.copies == []
    assert [AplansImage.objects.get(pk=row['pk']).file.name for row in rows] == [name] * 2


def test_a_shared_key_is_never_sent_down_the_single_row_restore_path():
    """
    A deleted shared key is both shared and missing.

    `restore_missing` consults only the first row, so routing it there would copy that row's bytes
    onto the key and leave every row still sharing them.
    """
    command = Command()
    shared = {'documents/a.pdf'}
    missing = {'documents/a.pdf', 'documents/b.pdf'}

    assert command.choose_repair('documents/a.pdf', shared, missing, None) == 'shared'
    assert command.choose_repair('documents/a.pdf', shared, missing, 'shared') == 'shared'
    assert command.choose_repair('documents/a.pdf', shared, missing, 'missing') == 'skip'

    assert command.choose_repair('documents/b.pdf', shared, missing, None) == 'missing'
    assert command.choose_repair('documents/b.pdf', shared, missing, 'missing') == 'missing'
    assert command.choose_repair('documents/b.pdf', shared, missing, 'shared') == 'skip'

    assert command.choose_repair('documents/c.pdf', shared, missing, None) == 'skip'
