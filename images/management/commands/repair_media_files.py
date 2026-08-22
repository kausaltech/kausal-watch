from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count, FileField

from aplans.media_integrity import (
    content_ever_changed,
    current_version,
    existing_names,
    is_currently_deleted,
    list_versions,
    match_version_for_row,
    recovery_client,
    s3_storage,
    storage_key,
    version_sha1,
)

from documents.models import AplansDocument
from images.models import AplansImage

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from django.db.models import Model


class UnresolvedError(Exception):
    """Raised when a row's original content can't be identified with enough confidence to act."""


class Command(BaseCommand):
    help = (
        'Give every media object its own storage key, and restore files that were deleted along with a '
        'sibling that shared their key. Reports what it would do unless --execute is passed.'
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            '--execute',
            action='store_true',
            help='Actually copy objects and update rows. Without it, nothing is written anywhere.',
        )
        parser.add_argument(
            '--only',
            choices=['shared', 'missing'],
            help='Repair only shared keys, or only files missing from storage (default: both)',
        )
        parser.add_argument(
            '--keys-file',
            help='Repair only the `file` values listed in this file, one per line. Also skips discovery, '
            'so the credential in use need not be allowed to list the bucket.',
        )

    def handle(self, *args, **options) -> None:
        self.execute_repairs: bool = options['execute']
        wanted: set[str] | None = None
        if options['keys_file']:
            wanted = {line.strip() for line in Path(options['keys_file']).read_text().splitlines() if line.strip()}
            if not wanted:
                raise CommandError(f'No keys found in {options["keys_file"]}')

        if not self.execute_repairs:
            self.stdout.write(self.style.WARNING('Dry run -- pass --execute to apply. Nothing will be written.\n'))

        repaired = skipped = 0
        for model in (AplansImage, AplansDocument):
            model_repaired, model_skipped = self.repair_model(model, wanted=wanted, only=options['only'])
            repaired += model_repaired
            skipped += model_skipped

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'{repaired} row(s) repaired, {skipped} left for review'))

    def repair_model(self, model: type[Model], *, wanted: set[str] | None, only: str | None) -> tuple[int, int]:
        manager = model._default_manager
        file_field = model._meta.get_field('file')
        assert isinstance(file_field, FileField)
        storage = s3_storage(file_field.storage)
        client = recovery_client(storage)
        bucket = storage.bucket_name

        if getattr(storage, 'file_overwrite', False):
            # `get_available_name` would hand back the key that is already taken, so every "move"
            # would silently be a no-op onto the same object -- and new uploads would keep colliding.
            raise CommandError(
                'Storage is configured with file_overwrite=True; deploy the de-duplicating storage '
                'settings before repairing, or the repair cannot allocate distinct keys'
            )

        self.stdout.write(self.style.MIGRATE_HEADING(f'=== {model.__name__} (bucket {bucket}) ==='))

        rows_by_name: dict[str, list[dict]] = defaultdict(list)
        for row in manager.exclude(file='').values('pk', 'file', 'file_hash', 'file_size'):
            if wanted is None or row['file'] in wanted:
                rows_by_name[row['file']].append(row)
        for rows in rows_by_name.values():
            rows.sort(key=lambda row: row['pk'])

        shared_names = {
            entry['file'] for entry in manager.exclude(file='').values('file').annotate(n=Count('pk')).filter(n__gt=1)
        }
        missing_names = self.find_missing(file_field.storage, set(rows_by_name), shared_names, wanted=wanted)

        repaired = skipped = 0
        for name in sorted(rows_by_name):
            rows = rows_by_name[name]
            if name in shared_names and only != 'missing':
                done, left = self.unshare(model, client, storage, file_field, bucket, name, rows)
            elif name in missing_names and only != 'shared':
                done, left = self.restore_missing(client, storage, bucket, name, rows)
            else:
                continue
            repaired += done
            skipped += left
        return repaired, skipped

    def find_missing(self, storage: Any, names: set[str], shared_names: set[str], *, wanted: set[str] | None) -> set[str]:
        """Return the names whose file is gone from storage, skipping discovery for an explicit key list."""
        if wanted is not None:
            # Nothing to discover: whether a key is missing falls out of its version listing instead,
            # which avoids needing `s3:ListBucket` on the credential doing the repair.
            return names - shared_names
        return names - existing_names(storage, names)

    def unshare(
        self,
        model: type[Model],
        client: Any,
        storage: Any,
        file_field: FileField,
        bucket: str,
        name: str,
        rows: list[dict],
    ) -> tuple[int, int]:
        """
        Give every row on a shared key an object of its own, restoring content where it differs.

        All or nothing: unless every row can be traced to the bytes it recorded, the group is left
        exactly as it is. A partial repair would move some rows while the keeper and the
        unresolvable ones went on sharing a key, which is harder to reason about than the original
        problem and hides the rows that still need attention.
        """
        key = storage_key(storage, name)
        versions, markers = list_versions(client, bucket, key)
        pks = [row['pk'] for row in rows]
        if not versions:
            self.warn(f'{name!r}: shared by {pks} but has no versions in storage')
            return 0, len(rows)

        deleted = is_currently_deleted(versions, markers)
        try:
            keeper, plan = self.plan_group(client, bucket, key, versions, rows, deleted=deleted)
        except UnresolvedError as e:
            self.warn(f'{name!r}: {e}; group left untouched')
            return 0, len(rows)

        others = [row for row in rows if row['pk'] != keeper['pk']]
        state = ' (currently deleted)' if deleted else ''
        self.stdout.write(f'{name!r}{state}: row {keeper["pk"]} keeps the key; {len(others)} row(s) move')

        repaired = 0
        if deleted:
            # The keeper would otherwise be left holding a key with a delete marker on top.
            keeper_version = plan[keeper['pk']]
            self.stdout.write(f'  row {keeper["pk"]}: restoring version {keeper_version} onto the shared key')
            if self.execute_repairs:
                client.copy_object(
                    Bucket=bucket,
                    Key=key,
                    CopySource={'Bucket': bucket, 'Key': key, 'VersionId': keeper_version},
                    **self.copy_extra(storage),
                )
            repaired += 1

        for row in others:
            new_name = self.copy_to_new_key(model, client, storage, file_field, bucket, key, name, row, plan[row['pk']])
            self.stdout.write(f'  row {row["pk"]} -> {new_name!r}')
            repaired += 1
        return repaired, 0

    def plan_group(
        self, client: Any, bucket: str, key: str, versions: list[dict], rows: list[dict], *, deleted: bool
    ) -> tuple[dict, dict[Any, str]]:
        """
        Decide which row keeps the key and which version every row's own copy comes from.

        Raises `UnresolvedError` unless all of that is settled, so the caller can leave the group
        untouched rather than repair it halfway.
        """
        plan: dict[Any, str] = {}
        for row in rows:
            version_id = match_version_for_row(client, bucket, key, row, versions)
            if version_id is None:
                raise UnresolvedError(f'row {row["pk"]} cannot be traced to a stored version')
            plan[row['pk']] = version_id

        if deleted or not content_ever_changed(versions):
            # Either nothing is currently under the key to anchor the choice, or every row wants
            # the same bytes. The oldest row is then as good a keeper as any.
            return rows[0], plan

        current = current_version(versions)
        if current is None:
            raise UnresolvedError('no current version despite the key not being deleted')
        current_hash = version_sha1(client, bucket, key, current)
        keepers = [row for row in rows if row['file_hash'] == current_hash]
        if not keepers:
            raise UnresolvedError(f'no row matches the current content ({current_hash[:12]}...)')
        return keepers[0], plan

    def restore_missing(self, client: Any, storage: Any, bucket: str, name: str, rows: list[dict]) -> tuple[int, int]:
        """
        Put the version whose bytes the row recorded back as the current one.

        Copying forward rather than removing the delete marker keeps the history intact and needs no
        `s3:DeleteObjectVersion`, which the credential doing the repair may not have. The version is
        chosen by hash rather than recency: where a sibling overwrote this key before being deleted,
        the newest surviving version holds the sibling's bytes, and restoring it would quietly give
        the row a file that was never its own.
        """
        key = storage_key(storage, name)
        versions, markers = list_versions(client, bucket, key)
        pks = [row['pk'] for row in rows]
        if not versions:
            self.warn(f'{name!r}: missing, and no version survives to restore from')
            return 0, len(rows)
        if not is_currently_deleted(versions, markers):
            self.stdout.write(f'{name!r}: present after all; nothing to restore')
            return 0, 0

        version_id = match_version_for_row(client, bucket, key, rows[0], versions)
        if version_id is None:
            self.warn(f'{name!r}: no stored version matches what row {rows[0]["pk"]} recorded; needs manual review')
            return 0, len(rows)

        self.stdout.write(f'{name!r}: restoring version {version_id} for row(s) {pks}')
        if self.execute_repairs:
            client.copy_object(
                Bucket=bucket,
                Key=key,
                CopySource={'Bucket': bucket, 'Key': key, 'VersionId': version_id},
                **self.copy_extra(storage),
            )
        return len(rows), 0

    def copy_to_new_key(
        self,
        model: type[Model],
        client: Any,
        storage: Any,
        file_field: FileField,
        bucket: str,
        key: str,
        name: str,
        row: dict,
        version_id: str,
    ) -> str:
        """Copy one version to a key of its own and point the row at it."""
        new_name = storage.get_available_name(name, max_length=file_field.max_length)
        if new_name == name:
            raise CommandError(f'Storage returned the same key {name!r} for a copy; refusing to overwrite it')
        if not self.execute_repairs:
            return new_name

        # Copy first: an unreferenced object is harmless, whereas a row pointing at a key that was
        # never written is exactly the breakage being repaired.
        client.copy_object(
            Bucket=bucket,
            Key=storage_key(storage, new_name),
            CopySource={'Bucket': bucket, 'Key': key, 'VersionId': version_id},
            **self.copy_extra(storage),
        )
        with transaction.atomic():
            # `update()` rather than `save()`: the bytes are unchanged, so file_hash and file_size
            # still hold, and there is no reason to touch revisions or re-render renditions.
            model._default_manager.filter(pk=row['pk']).update(file=new_name)
        return new_name

    def copy_extra(self, storage: Any) -> dict[str, Any]:
        acl = getattr(storage, 'default_acl', None)
        return {'ACL': acl} if acl else {}

    def warn(self, message: str) -> None:
        self.stderr.write(self.style.WARNING(message))
