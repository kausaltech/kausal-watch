from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.core.management.base import BaseCommand, CommandError
from django.db.models import FileField
from wagtail.models import Collection

from aplans.media_integrity import existing_names

from actions.models import Plan
from documents.models import AplansDocument
from images.models import AplansImage

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from django.db.models import Model

SAME = 'SAME'
"""Every row on the key recorded the same non-blank hash and size: nothing was lost to the overwrite."""

DIFFER = 'DIFFER'
"""The rows recorded different content, so the earlier bytes need to come from version history."""

UNKNOWN = 'UNKNOWN'
"""At least one row never recorded a hash, so nothing here can settle whether content was lost."""

MISSING = 'MISSING'
"""A row whose file is gone from storage. Reported per row rather than per group."""

RESIDUE = 'RESIDUE'
"""Every row on the key is owned by no plan, so the group is probably left over from seeding."""

NO_PLAN = 'NO-PLAN'
"""No plan's root collection is an ancestor of the row's collection."""

_EMITTED_KINDS = (SAME, DIFFER, UNKNOWN, MISSING, RESIDUE)


class PlanAttributor:
    """
    Name the plan that owns a collection, by walking the collection tree to a plan's root.

    Which plan a media object belongs to is what separates damage worth repairing from rows left
    behind by seeding one cluster's database from another's. Note that `NO-PLAN` is not by itself
    proof of that: the collection tree's own root and any collection created outside a plan land
    there too.
    """

    def __init__(self) -> None:
        roots = (
            (plan.root_collection.path, plan.identifier)
            for plan in Plan.objects.filter(root_collection__isnull=False).select_related('root_collection')
        )
        # Longest path first, so a plan nested under another plan's collection wins over its ancestor.
        self.roots = sorted(roots, key=lambda root: -len(root[0]))
        self.paths: dict[Any, str] = dict(Collection.objects.values_list('pk', 'path'))

    def of(self, collection_id: Any) -> str:
        path = self.paths.get(collection_id)
        if path is None:
            return 'no-collection'
        for root_path, identifier in self.roots:
            if path.startswith(root_path):
                return identifier
        return NO_PLAN


class Command(BaseCommand):
    help = (
        'Triage the media files that more than one object points at, using only what the rows recorded at '
        'upload time. Says which shared keys lost content and which merely need keys of their own, and '
        'attributes every affected row to a plan.'
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            '--emit-keys',
            metavar='DIR',
            help='Write the `file` values of each verdict to DIR as same-keys.txt, differ-keys.txt, '
            'unknown-keys.txt, residue-keys.txt and (with --include-missing) missing-keys.txt, ready to '
            'pass to repair_media_files --keys-file',
        )
        parser.add_argument(
            '--include-missing',
            action='store_true',
            help='Also attribute the rows whose file is gone from storage. Needs to list the bucket, '
            'which the pure database triage does not.',
        )

    def handle(self, *args, **options) -> None:
        emit_dir: str | None = options['emit_keys']
        if emit_dir is not None and not Path(emit_dir).is_dir():
            raise CommandError(f'{emit_dir!r} is not a directory')

        self.attributor = PlanAttributor()
        keys: dict[str, list[str]] = {kind: [] for kind in _EMITTED_KINDS}

        for model in (AplansImage, AplansDocument):
            self.stdout.write(self.style.MIGRATE_HEADING(f'=== {model.__name__}'))
            counts = self.report_shared(model, keys)
            if options['include_missing']:
                counts += self.report_missing(model, keys)
            self.stdout.write(f'--- {model.__name__}: {dict(sorted(counts.items()))}')

        if emit_dir is not None:
            determined = {SAME, DIFFER, UNKNOWN, RESIDUE}
            if options['include_missing']:
                determined.add(MISSING)
            self.emit_keys(Path(emit_dir), keys, determined=determined)

    def report_shared(self, model: type[Model], keys: dict[str, list[str]]) -> Counter[str]:
        groups: dict[str, list[dict]] = defaultdict(list)
        fields = ('pk', 'file', 'file_hash', 'file_size', 'collection_id', 'created_at')
        for row in model._default_manager.exclude(file='').values(*fields):
            groups[row['file']].append(row)

        counts: Counter[str] = Counter()
        for name in sorted(groups):
            rows = sorted(groups[name], key=lambda row: row['pk'])
            if len(rows) < 2:
                continue
            verdict = self.verdict_of(rows)
            counts[verdict] += 1
            keys[verdict].append(name)

            plans = {self.attributor.of(row['collection_id']) for row in rows}
            if plans == {NO_PLAN}:
                counts['residue'] += 1
                keys[RESIDUE].append(name)

            self.stdout.write(f'{verdict:8} {len(rows)}x {name}')
            self.stdout.write(f'         {self.describe(rows)}')
        return counts

    def report_missing(self, model: type[Model], keys: dict[str, list[str]]) -> Counter[str]:
        rows = list(model._default_manager.exclude(file='').values('pk', 'file', 'file_hash', 'file_size', 'collection_id'))
        if not rows:
            return Counter()

        file_field = model._meta.get_field('file')
        assert isinstance(file_field, FileField)
        existing = existing_names(file_field.storage, {row['file'] for row in rows})

        counts: Counter[str] = Counter()
        for row in sorted((row for row in rows if row['file'] not in existing), key=lambda row: row['pk']):
            counts[MISSING] += 1
            keys[MISSING].append(row['file'])
            plan = self.attributor.of(row['collection_id'])
            if plan == NO_PLAN:
                counts['residue'] += 1
                keys[RESIDUE].append(row['file'])
            self.stdout.write(f'{MISSING:8} {row["file"]}')
            self.stdout.write(f'         {row["pk"]}:{row["file_size"]}:{(row["file_hash"] or "-")[:8]}:{plan}')
        return counts

    def verdict_of(self, rows: list[dict]) -> str:
        """
        Return what the rows' own records say about the shared object's content.

        A blank `file_hash` is never treated as a match: the column is populated lazily, so older
        rows have `''`, and calling two blanks equal would classify real data loss as harmless.
        """
        hashes = {row['file_hash'] or '' for row in rows}
        if '' in hashes:
            return UNKNOWN
        if len(hashes) > 1:
            return DIFFER
        return SAME if len({row['file_size'] for row in rows}) == 1 else DIFFER

    def describe(self, rows: list[dict]) -> str:
        return ' '.join(
            '{pk}:{date}:{size}:{hash}:{plan}'.format(
                pk=row['pk'],
                date=row['created_at'].date().isoformat(),
                size=row['file_size'],
                hash=(row['file_hash'] or '-')[:8],
                plan=self.attributor.of(row['collection_id']),
            )
            for row in rows
        )

    def emit_keys(self, directory: Path, keys: dict[str, list[str]], *, determined: set[str]) -> None:
        """
        Write one file per verdict, empty ones included, and delete the ones this run cannot answer.

        The documented procedure feeds these files straight to `repair_media_files --keys-file`, so a
        file left over from an earlier run would silently name keys that have since been repaired.
        Skipping a verdict with no findings is therefore not safe: it has to be truncated. A verdict
        this run did not determine at all -- `missing` without `--include-missing` -- is removed
        rather than written empty, since an empty file would assert that nothing is missing when the
        question was never asked. `repair_media_files` rejects an empty key file outright, so an
        emptied file fails loudly rather than repairing the wrong thing.
        """
        for kind in _EMITTED_KINDS:
            path = directory / f'{kind.lower()}-keys.txt'
            if kind not in determined:
                if path.exists():
                    path.unlink()
                    self.stdout.write(self.style.WARNING(f'Removed {path}: not determined by this run'))
                continue
            names = sorted(set(keys[kind]))
            path.write_text(''.join(f'{name}\n' for name in names))
            self.stdout.write(self.style.SUCCESS(f'Wrote {len(names)} key(s) to {path}'))
