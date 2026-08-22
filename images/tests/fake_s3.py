"""A canned S3 version history for exercising the media integrity commands without a bucket."""

from __future__ import annotations

import datetime
import hashlib
from io import BytesIO
from pathlib import PurePosixPath

BUCKET = 'test-bucket'


def sha1_hex(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()  # noqa: S324 -- matches Wagtail's file_hash


class FakeStorage:
    """
    Mimics Django's name allocation: a name is handed back only when nothing occupies it.

    Modelling occupancy matters, because a key with a delete marker on top reads as free — which is
    what makes a dry run allocate the very key it is moving a row off.
    """

    bucket_name = BUCKET
    default_acl = 'public-read'

    def __init__(self, *, present: set[str] | None = None) -> None:
        self.present = set(present or ())
        self._counter = 0

    def exists(self, name: str) -> bool:
        return name in self.present

    def get_alternative_name(self, file_root: str, file_ext: str) -> str:
        self._counter += 1
        return f'{file_root}.moved{self._counter}{file_ext}'

    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        while self.exists(name):
            path = PurePosixPath(name)
            name = self.get_alternative_name(str(path.with_suffix('')), path.suffix)
        return name


def moved(name: str, n: int = 1) -> str:
    """Return the name `FakeStorage` hands out for the n-th copy made off `name`."""
    path = PurePosixPath(name)
    return f'{path.with_suffix("")}.moved{n}{path.suffix}'


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
                'ETag': sha1_hex(data)[:32],
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
