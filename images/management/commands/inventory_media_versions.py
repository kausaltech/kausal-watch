from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, FileField

from aplans.media_integrity import (
    MISSING,
    classify_rows,
    content_ever_changed,
    current_version,
    existing_names,
    is_currently_deleted,
    list_versions,
    recovery_client,
    s3_storage,
    storage_key,
    version_sha1,
)

from documents.models import AplansDocument
from images.models import AplansImage

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from django.core.files.storage import Storage
    from django.db.models import Model


class Command(BaseCommand):
    help = 'Report S3 version history for media files that are shared by several objects or missing from storage'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            '--verify-hashes',
            action='store_true',
            help='Download candidate versions and compare SHA-1 against the recorded file_hash. Skipped '
            'automatically for keys whose versions all share one ETag, since those cannot have changed.',
        )
        parser.add_argument(
            '--keys-file',
            help='Inventory only the `file` values listed in this file, one per line, instead of discovering '
            'them. Use when the credential that can list version history cannot list the bucket itself.',
        )
        parser.add_argument('--json', dest='json_path', help='Write the full report to this path as JSON')

    def handle(self, *args, **options) -> None:
        wanted: set[str] | None = None
        if options['keys_file']:
            wanted = {line.strip() for line in Path(options['keys_file']).read_text().splitlines() if line.strip()}
            if not wanted:
                raise CommandError(f'No keys found in {options["keys_file"]}')

        report: dict[str, Any] = {}
        for model in (AplansImage, AplansDocument):
            report[model.__name__] = self.inventory(model, wanted=wanted, verify_hashes=options['verify_hashes'])

        if options['json_path']:
            Path(options['json_path']).write_text(json.dumps(report, indent=2, default=str))
            self.stdout.write(f'Wrote report to {options["json_path"]}')

    def inventory(self, model: type[Model], *, wanted: set[str] | None, verify_hashes: bool) -> dict[str, Any]:
        manager = model._default_manager
        file_field = model._meta.get_field('file')
        assert isinstance(file_field, FileField)
        storage = s3_storage(file_field.storage)
        client = recovery_client(storage)
        bucket = storage.bucket_name

        self.stdout.write(self.style.MIGRATE_HEADING(f'\n=== {model.__name__} (bucket {bucket}) ==='))

        rows_by_name: dict[str, list[dict]] = defaultdict(list)
        for row in manager.exclude(file='').values('pk', 'file', 'file_hash', 'file_size', 'created_at'):
            if wanted is None or row['file'] in wanted:
                rows_by_name[row['file']].append(row)

        shared_names = {
            entry['file'] for entry in manager.exclude(file='').values('file').annotate(n=Count('pk')).filter(n__gt=1)
        }
        names = self.names_to_inspect(file_field.storage, rows_by_name, shared_names, wanted=wanted)
        entries = [
            self.inspect(
                client,
                storage,
                bucket,
                name,
                rows_by_name[name],
                shared=name in shared_names,
                verify_hashes=verify_hashes,
            )
            for name in sorted(names)
        ]
        self.summarize(entries)
        return {'bucket': bucket, 'entries': entries}

    def names_to_inspect(
        self, storage: Storage, rows_by_name: dict[str, list[dict]], shared_names: set[str], *, wanted: set[str] | None
    ) -> set[str]:
        """
        Return the names worth inspecting: everything shared, plus anything gone from storage.

        With an explicit key list there is nothing to discover, which also avoids needing
        `s3:ListBucket` -- the permission the operator credential may lack.
        """
        if wanted is not None:
            return set(rows_by_name)
        present = existing_names(storage, set(rows_by_name))
        return shared_names | (set(rows_by_name) - present)

    def inspect(
        self, client: Any, storage: Any, bucket: str, name: str, rows: list[dict], *, shared: bool, verify_hashes: bool
    ) -> dict[str, Any]:
        key = storage_key(storage, name)
        versions, markers = list_versions(client, bucket, key)
        changed = content_ever_changed(versions)

        entry: dict[str, Any] = {
            'file': name,
            'key': key,
            'kind': classify_rows(rows) if shared else MISSING,
            'shared': shared,
            'content_ever_changed': changed,
            'rows': rows,
            'delete_markers': [{'VersionId': m['VersionId'], 'LastModified': m['LastModified']} for m in markers],
        }
        entry['deleted'] = is_currently_deleted(versions, markers)

        entry['verified'] = bool(verify_hashes)
        if verify_hashes and versions:
            # With a single content spanning the history, hashing one version settles every row;
            # only a history that actually changed needs each version fetched. A delete marker on
            # top leaves no current version, but the surviving ones are still the row's candidates
            # -- which is exactly the case repair_media_files can restore.
            representative = current_version(versions) or versions[-1]
            targets = versions if changed else [representative]
            for version in targets:
                version_sha1(client, bucket, key, version)

        # Reported after any hashing, so the digests travel with the versions into the JSON report.
        reported_fields = ('VersionId', 'Size', 'ETag', 'LastModified', 'IsLatest', 'sha1')
        entry['versions'] = [{field: version[field] for field in reported_fields if field in version} for version in versions]
        entry['matched'] = self.match_rows(rows, entry['versions'], by='sha1' if verify_hashes else 'Size')

        entry['recoverable'] = self.is_recoverable(entry)
        self.report(entry)
        return entry

    def match_rows(self, rows: list[dict], versions: list[dict], *, by: str) -> dict[str, Any]:
        """Match each row to the versions whose size or hash agrees with what the row recorded."""
        row_key = 'file_hash' if by == 'sha1' else 'file_size'
        matched: dict[str, Any] = {}
        for row in rows:
            wanted = row[row_key]
            matched[str(row['pk'])] = [v['VersionId'] for v in versions if wanted is not None and v.get(by) == wanted]
        return matched

    def is_recoverable(self, entry: dict[str, Any]) -> bool:
        """
        Return whether every row could be given the bytes it recorded.

        This mirrors `match_version_for_row`, which is what the repair actually runs: a verdict the
        repair would not honour is worse than no verdict at all.
        """
        if not entry['versions']:
            return False
        return all(self.row_resolves(entry, row) for row in entry['rows'])

    def row_resolves(self, entry: dict[str, Any], row: dict[str, Any]) -> bool:
        """
        Return whether one row can be traced to a stored version.

        A row that recorded no hash resolves only by elimination, when a single content spans the
        history. A row that did record one needs a version to match it: a single-content history is
        no help if versioning began after a sibling had already overwritten the key, since the only
        surviving bytes are then the sibling's.
        """
        if not row['file_hash']:
            return not entry['content_ever_changed']
        return bool(entry['matched'].get(str(row['pk'])))

    def report(self, entry: dict[str, Any]) -> None:
        pks = [row['pk'] for row in entry['rows']]
        style = self.style.SUCCESS if entry['recoverable'] else self.style.ERROR
        verdict = 'recoverable' if entry['recoverable'] else 'NEEDS REVIEW'
        deleted = ' deleted' if entry['deleted'] else ''
        basis = '' if entry['verified'] else ' (size-matched only)'
        self.stdout.write(
            style(
                f'{entry["kind"]:<15} {entry["file"]!r} rows={pks} versions={len(entry["versions"])} '
                f'markers={len(entry["delete_markers"])}{deleted} -> {verdict}{basis}'
            )
        )

    def summarize(self, entries: list[dict[str, Any]]) -> None:
        by_kind: dict[str, list[dict]] = defaultdict(list)
        for entry in entries:
            by_kind[entry['kind']].append(entry)
        self.stdout.write('')
        for kind, group in sorted(by_kind.items()):
            recoverable = sum(1 for e in group if e['recoverable'])
            self.stdout.write(f'  {kind:<15} {len(group):>3} group(s), {recoverable} recoverable')
