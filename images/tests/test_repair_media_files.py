from __future__ import annotations

import datetime
import hashlib
from io import BytesIO

from django.core.management.base import CommandError

import pytest

from aplans.media_integrity import current_version, is_currently_deleted, list_versions

from images.management.commands.repair_media_files import Command, UnresolvedError
from images.models import AplansImage
from images.tests.factories import AplansImageFactory

pytestmark = pytest.mark.django_db

BUCKET = 'test-bucket'
FILE_FIELD = AplansImage._meta.get_field('file')


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()  # noqa: S324 -- matches Wagtail's file_hash


class FakeStorage:
    bucket_name = BUCKET
    default_acl = 'public-read'

    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        return f'{name}.moved'


class FakePaginator:
    def __init__(self, versions: list[dict], markers: list[dict]) -> None:
        self.versions = versions
        self.markers = markers

    def paginate(self, **_kwargs):
        return [{'Versions': self.versions, 'DeleteMarkers': self.markers}]


class FakeClient:
    """
    Serves a canned version history and records every copy_object call.

    `contents` is oldest-first. `api_order='newest_first'` mimics how S3 actually returns listings,
    and `same_timestamp` collapses LastModified so that only `IsLatest` distinguishes the current
    version -- the tie the real API can produce for uploads seconds apart.
    """

    def __init__(
        self,
        key: str,
        contents: list[bytes],
        *,
        deleted: bool = False,
        stale_marker: bool = False,
        same_timestamp: bool = False,
        api_order: str = 'oldest_first',
    ) -> None:
        base = datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
        self.bodies = {f'v{i}': data for i, data in enumerate(contents)}
        newest = len(contents) - 1
        self.versions = [
            {
                'Key': key,
                'VersionId': f'v{i}',
                'ETag': _sha1(data)[:32],
                'Size': len(data),
                'LastModified': base if same_timestamp else base + datetime.timedelta(minutes=i),
                'IsLatest': i == newest and not deleted,
            }
            for i, data in enumerate(contents)
        ]
        if api_order == 'newest_first':
            self.versions.reverse()
        self.markers = []
        if deleted or stale_marker:
            self.markers = [
                {
                    'Key': key,
                    'VersionId': 'dm',
                    'LastModified': base + datetime.timedelta(hours=1 if deleted else -1),
                    'IsLatest': deleted,
                }
            ]
        self.copies: list[dict] = []

    def get_paginator(self, _name: str) -> FakePaginator:
        return FakePaginator(self.versions, self.markers)

    def get_object(self, Bucket: str, Key: str, VersionId: str) -> dict:  # noqa: N803 -- boto3 casing
        return {'Body': BytesIO(self.bodies[VersionId])}

    def copy_object(self, **kwargs) -> dict:
        self.copies.append(kwargs)
        return {}


def _shared_images(count: int, *, hashes: list[str] | None = None) -> list[dict]:
    images = [AplansImageFactory.create() for _ in range(count)]
    pks = [image.pk for image in images]
    name = images[0].file.name
    AplansImage.objects.filter(pk__in=pks).update(file=name, file_hash='h', file_size=4)
    if hashes is not None:
        for pk, file_hash in zip(sorted(pks), hashes, strict=True):
            AplansImage.objects.filter(pk=pk).update(file_hash=file_hash)
    return _rows(pks)


def _rows(pks: list[int]) -> list[dict]:
    return list(AplansImage.objects.filter(pk__in=pks).order_by('pk').values('pk', 'file', 'file_hash', 'file_size'))


def _command(*, execute: bool = True) -> Command:
    command = Command()
    command.execute_repairs = execute
    return command


def _unshare(client: FakeClient, rows: list[dict], storage: FakeStorage | None = None) -> tuple[int, int]:
    return _command().unshare(AplansImage, client, storage or FakeStorage(), FILE_FIELD, BUCKET, rows[0]['file'], rows)


def test_identical_content_keeps_the_oldest_row_and_moves_the_rest():
    rows = _shared_images(3)
    name = rows[0]['file']
    client = FakeClient(name, [b'same', b'same'])

    assert _unshare(client, rows) == (2, 0)

    assert AplansImage.objects.get(pk=rows[0]['pk']).file.name == name
    assert AplansImage.objects.get(pk=rows[1]['pk']).file.name == f'{name}.moved'
    assert len(client.copies) == 2
    assert {c['CopySource']['VersionId'] for c in client.copies} == {'v1'}
    assert {c['ACL'] for c in client.copies} == {'public-read'}


def test_dry_run_writes_nothing():
    rows = _shared_images(2)
    name = rows[0]['file']
    client = FakeClient(name, [b'same', b'same'])

    _command(execute=False).unshare(AplansImage, client, FakeStorage(), FILE_FIELD, BUCKET, name, rows)

    assert client.copies == []
    assert AplansImage.objects.get(pk=rows[1]['pk']).file.name == name


def test_overwritten_content_restores_each_row_from_its_own_version():
    old, new = b'old-content', b'new'
    rows = _shared_images(2, hashes=[_sha1(old), _sha1(new)])
    client = FakeClient(rows[0]['file'], [old, new])

    assert _unshare(client, rows) == (1, 0)

    # The row matching the current bytes keeps the key; the overwritten one is restored elsewhere.
    assert AplansImage.objects.get(pk=rows[1]['pk']).file.name == rows[0]['file']
    assert AplansImage.objects.get(pk=rows[0]['pk']).file.name == f'{rows[0]["file"]}.moved'
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
    rows = _shared_images(3, hashes=['', _sha1(b'two'), ''])
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

    assert _unshare(client, rows) == (2, 0)

    # One copy puts the keeper's content back on the shared key, the other moves the second row.
    onto_key = [c for c in client.copies if c['Key'] == name]
    moved = [c for c in client.copies if c['Key'] == f'{name}.moved']
    assert len(onto_key) == 1
    assert len(moved) == 1
    assert AplansImage.objects.get(pk=rows[1]['pk']).file.name == f'{name}.moved'


def test_current_version_uses_is_latest_when_timestamps_tie():
    """Second-granularity timestamps cannot order uploads made within the same second."""
    client = FakeClient('k', [b'old', b'new'], same_timestamp=True, api_order='newest_first')

    versions, _markers = list_versions(client, BUCKET, 'k')

    assert versions[-1]['VersionId'] == 'v0'  # recency order is useless here
    assert current_version(versions)['VersionId'] == 'v1'


def test_keeper_is_chosen_by_is_latest_not_by_timestamp_order():
    old, new = b'old', b'new'
    rows = _shared_images(2, hashes=[_sha1(old), _sha1(new)])
    name = rows[0]['file']
    client = FakeClient(name, [old, new], same_timestamp=True, api_order='newest_first')

    assert _unshare(client, rows) == (1, 0)

    assert AplansImage.objects.get(pk=rows[1]['pk']).file.name == name
    assert client.copies[0]['CopySource']['VersionId'] == 'v0'


def test_missing_file_is_restored_from_the_version_it_recorded():
    own = b'gone'
    image = AplansImageFactory.create()
    AplansImage.objects.filter(pk=image.pk).update(file_hash=_sha1(own))
    rows = _rows([image.pk])
    name = rows[0]['file']
    client = FakeClient(name, [own], deleted=True)

    assert _command().restore_missing(AplansImage, client, FakeStorage(), BUCKET, name, rows) == (1, 0)

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
    AplansImage.objects.filter(pk=image.pk).update(file_hash=_sha1(own))
    rows = _rows([image.pk])
    name = rows[0]['file']
    client = FakeClient(name, [own, sibling], deleted=True)

    assert _command().restore_missing(AplansImage, client, FakeStorage(), BUCKET, name, rows) == (1, 0)

    assert client.copies[0]['CopySource']['VersionId'] == 'v0'


def test_missing_file_with_no_matching_version_is_left_for_review():
    image = AplansImageFactory.create()
    AplansImage.objects.filter(pk=image.pk).update(file_hash='not-in-storage')
    rows = _rows([image.pk])
    name = rows[0]['file']
    client = FakeClient(name, [b'one', b'two'], deleted=True)

    assert _command().restore_missing(AplansImage, client, FakeStorage(), BUCKET, name, rows) == (0, 1)

    assert client.copies == []


def test_missing_file_without_versions_is_reported_not_repaired():
    image = AplansImageFactory.create()
    rows = _rows([image.pk])
    name = rows[0]['file']
    client = FakeClient(name, [], deleted=True)

    assert _command().restore_missing(AplansImage, client, FakeStorage(), BUCKET, name, rows) == (0, 1)

    assert client.copies == []


def test_a_stale_delete_marker_does_not_trigger_a_restore():
    """The key is present; an older delete marker further down the history is not a deletion."""
    image = AplansImageFactory.create()
    rows = _rows([image.pk])
    name = rows[0]['file']
    client = FakeClient(name, [b'here'], stale_marker=True)
    versions, markers = list_versions(client, BUCKET, name)
    assert is_currently_deleted(versions, markers) is False

    assert _command().restore_missing(AplansImage, client, FakeStorage(), BUCKET, name, rows) == (0, 0)

    assert client.copies == []


def test_refuses_to_copy_when_storage_hands_back_the_same_key():
    """
    With `file_overwrite=True` the storage returns the key that is already taken.

    Copying onto it would be a silent no-op reported as a successful move.
    """

    class OverwritingStorage(FakeStorage):
        def get_available_name(self, name: str, max_length: int | None = None) -> str:
            return name

    rows = _shared_images(2)
    client = FakeClient(rows[0]['file'], [b'same', b'same'])

    with pytest.raises(CommandError, match='refusing to overwrite'):
        _unshare(client, rows, OverwritingStorage())

    assert client.copies == []
