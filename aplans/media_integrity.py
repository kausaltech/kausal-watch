"""Helpers shared by the media integrity check, the S3 version inventory, and the repair command."""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from django.core.management.base import CommandError

if TYPE_CHECKING:
    from django.core.files.storage import Storage


def split_path(name: str) -> tuple[str, str]:
    path = PurePosixPath(name)
    directory = str(path.parent)
    return ('' if directory == '.' else directory), path.name


def join_path(directory: str, basename: str) -> str:
    return f'{directory}/{basename}' if directory else basename


def existing_names(storage: Storage, names: set[str]) -> set[str]:
    """
    Return the subset of `names` that exists on `storage`.

    Each directory is listed once instead of checking every name on its own, so the number of
    storage requests stays proportional to the number of directories rather than to the number of
    files. Storages that can't list a directory fall back to per-file existence checks.
    """
    basenames_by_directory: dict[str, set[str]] = defaultdict(set)
    for name in names:
        directory, basename = split_path(name)
        basenames_by_directory[directory].add(basename)

    existing: set[str] = set()
    for directory, basenames in basenames_by_directory.items():
        try:
            _, listed = storage.listdir(directory)
        except FileNotFoundError, NotImplementedError, OSError:
            existing.update(
                join_path(directory, basename) for basename in basenames if storage.exists(join_path(directory, basename))
            )
            continue
        existing.update(join_path(directory, basename) for basename in basenames.intersection(listed))
    return existing


# Environment variables holding an operator credential for the versioning API. The application's
# own key is not necessarily allowed to read version history: on de-prod the bucket policy grants
# it `s3:ListBucket` but not `s3:ListBucketVersions`, so the two have to be kept separate.
RECOVERY_ACCESS_KEY_ENV = 'MEDIA_RECOVERY_S3_ACCESS_KEY_ID'
RECOVERY_SECRET_KEY_ENV = 'MEDIA_RECOVERY_S3_SECRET_ACCESS_KEY'  # noqa: S105 -- a variable name, not a secret

# Classifications for a group of rows that share one storage key.
LOSSLESS = 'lossless'
"""Every row recorded the same hash, so the shared object is the content all of them expect."""

OVERWRITTEN = 'overwritten'
"""Rows recorded different hashes: the earlier ones were overwritten and need version history."""

UNKNOWN_HASHES = 'unknown-hashes'
"""At least one row has no recorded hash, so `file_hash` can't settle whether content was lost."""

MISSING = 'missing'
"""A single row whose file is gone from storage."""


def s3_storage(storage: Storage) -> Any:
    """
    Return the underlying S3 storage, unwrapping the local-with-fallback backend.

    Version history only exists on S3, so a purely local storage is a hard error rather than an
    empty report -- otherwise a misconfigured environment would look like "nothing to recover".
    """
    inner = getattr(storage, 's3_storage', storage)
    if not hasattr(inner, 'bucket_name'):
        raise CommandError(f'Storage {type(storage).__name__} is not S3-backed; version history is unavailable')
    return inner


def recovery_client(storage: Any) -> Any:
    """
    Return a client for the versioning API, preferring an operator credential from the environment.

    Falls back to the storage's own client when no operator credential is configured.
    """
    access_key = os.environ.get(RECOVERY_ACCESS_KEY_ENV)
    secret_key = os.environ.get(RECOVERY_SECRET_KEY_ENV)
    if not access_key or not secret_key:
        return storage.connection.meta.client

    import boto3

    return boto3.client(
        's3',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        endpoint_url=storage.endpoint_url,
        region_name=storage.region_name,
        config=storage.client_config,
    )


def storage_key(storage: Any, name: str) -> str:
    """Map a `file` value to the real bucket key, which is prefixed when `location` is configured."""
    normalize = getattr(storage, '_normalize_name', None)
    clean = getattr(storage, '_clean_name', None)
    if normalize is None or clean is None:
        return name
    return normalize(clean(name))


def list_versions(client: Any, bucket: str, key: str) -> tuple[list[dict], list[dict]]:
    """
    Return `(versions, delete_markers)` for exactly `key`, oldest first.

    `list_object_versions` takes a prefix, so keys that merely start with `key` come back too and
    have to be filtered out. The ordering is for display only: `LastModified` has second
    granularity on most S3 implementations, and the uploads that caused this mess were often
    seconds apart, so which entry is current must come from `IsLatest` instead.
    """
    versions: list[dict] = []
    markers: list[dict] = []
    paginator = client.get_paginator('list_object_versions')
    for page in paginator.paginate(Bucket=bucket, Prefix=key):
        versions.extend(v for v in page.get('Versions', []) if v['Key'] == key)
        markers.extend(m for m in page.get('DeleteMarkers', []) if m['Key'] == key)
    versions.sort(key=lambda v: v['LastModified'])
    markers.sort(key=lambda m: m['LastModified'])
    return versions, markers


def sha1_of_version(client: Any, bucket: str, key: str, version_id: str) -> str:
    body = client.get_object(Bucket=bucket, Key=key, VersionId=version_id)['Body']
    hasher = hashlib.sha1()  # noqa: S324 -- matches Wagtail's `hash_filelike`, not used for security
    for chunk in iter(lambda: body.read(1024 * 1024), b''):
        hasher.update(chunk)
    return hasher.hexdigest()


def classify_rows(rows: list[dict]) -> str:
    hashes = {row['file_hash'] for row in rows}
    if '' in hashes or None in hashes:
        return UNKNOWN_HASHES
    return LOSSLESS if len(hashes) == 1 else OVERWRITTEN


def content_ever_changed(versions: list[dict]) -> bool:
    """
    Return whether the bytes under this key ever differed between versions.

    Equal ETags imply equal content, so a single distinct ETag proves nothing was overwritten --
    for free, straight out of the listing. The converse does not hold: multipart uploads of
    identical content can differ in ETag when part sizes differ, so unequal ETags only mean
    "unknown", which is what `--verify-hashes` is for.
    """
    return len({v['ETag'] for v in versions}) > 1


def current_version(versions: list[dict]) -> dict | None:
    """
    Return the version that is currently served under the key, or None when a deletion is on top.

    `IsLatest` is authoritative; timestamp order is only a fallback for backends that omit it,
    and cannot break ties between versions written in the same second.
    """
    if not versions:
        return None
    if not any('IsLatest' in version for version in versions):
        return versions[-1]
    latest = [version for version in versions if version.get('IsLatest')]
    return latest[0] if latest else None


def is_currently_deleted(versions: list[dict], markers: list[dict]) -> bool:
    """Return whether a delete marker is the current state of the key."""
    if not markers:
        return False
    if any(marker.get('IsLatest') for marker in markers):
        return True
    if any('IsLatest' in entry for entry in (*versions, *markers)):
        return False
    return not versions or markers[-1]['LastModified'] > versions[-1]['LastModified']


def version_sha1(client: Any, bucket: str, key: str, version: dict) -> str:
    """Return the SHA-1 of a version's bytes, caching it on the version dict."""
    if 'sha1' not in version:
        version['sha1'] = sha1_of_version(client, bucket, key, version['VersionId'])
    return version['sha1']


def distinct_contents(client: Any, bucket: str, key: str, versions: list[dict]) -> set[str]:
    """
    Return the distinct SHA-1s across `versions`, hashing only when ETags leave the question open.

    Equal ETags prove equal content, so one hash stands for the whole history. Unequal ETags prove
    nothing -- multipart uploads of identical bytes differ in ETag when their part sizes differ,
    which happens readily when one version was PUT and another was produced by a server-side copy.
    Treating that as "the content changed" would strand recoverable keys, so the bytes decide.
    """
    if not versions:
        return set()
    if not content_ever_changed(versions):
        return {version_sha1(client, bucket, key, current_version(versions) or versions[-1])}
    return {version_sha1(client, bucket, key, version) for version in versions}


def match_version_for_row(client: Any, bucket: str, key: str, row: dict, versions: list[dict]) -> str | None:
    """
    Return the id of the version holding the bytes `row` recorded, or None if that can't be settled.

    The version is never chosen by recency. When a sibling overwrote this key and was then deleted,
    the newest surviving version holds the *sibling's* bytes, so restoring it would hand the row a
    file that was never its own.

    A recorded `file_hash` is always checked against the bytes themselves. A key whose history holds
    a single content is *not* evidence that the content is this row's: where versioning was switched
    on after the overwrite, the only surviving content is the sibling's, and the row's hash is the
    one thing that reveals it. The single-content inference is therefore reserved for rows that
    never recorded a hash, where nothing better exists -- and even then the history is judged by
    content rather than by ETag, so identical bytes uploaded with different part sizes still count
    as one content.
    """
    if not versions:
        return None
    file_hash = row.get('file_hash')
    if not file_hash:
        # Nothing recorded to match against, so the row resolves only if the history holds a single
        # content. ETags alone cannot establish that, so disagreeing ones are checked by hashing.
        if len(distinct_contents(client, bucket, key, versions)) > 1:
            return None
        only = current_version(versions) or versions[-1]
        return only['VersionId']
    if not content_ever_changed(versions):
        # One content spans the history, so one hash settles it -- no need to fetch the rest.
        only = current_version(versions) or versions[-1]
        return only['VersionId'] if version_sha1(client, bucket, key, only) == file_hash else None
    for version in versions:
        if version_sha1(client, bucket, key, version) == file_hash:
            return version['VersionId']
    return None
