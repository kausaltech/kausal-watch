from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, FileField

from documents.models import AplansDocument
from images.models import AplansImage, AplansRendition

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from django.core.files.storage import Storage
    from django.db.models import Model


def _split_path(name: str) -> tuple[str, str]:
    path = PurePosixPath(name)
    directory = str(path.parent)
    return ('' if directory == '.' else directory), path.name


def _join_path(directory: str, basename: str) -> str:
    return f'{directory}/{basename}' if directory else basename


def _existing_names(storage: Storage, names: set[str]) -> set[str]:
    """
    Return the subset of `names` that exists on `storage`.

    Each directory is listed once instead of checking every name on its own, so the number of
    storage requests stays proportional to the number of directories rather than to the number of
    files. Storages that can't list a directory fall back to per-file existence checks.
    """
    basenames_by_directory: dict[str, set[str]] = defaultdict(set)
    for name in names:
        directory, basename = _split_path(name)
        basenames_by_directory[directory].add(basename)

    existing: set[str] = set()
    for directory, basenames in basenames_by_directory.items():
        try:
            _, listed = storage.listdir(directory)
        except FileNotFoundError, NotImplementedError, OSError:
            existing.update(
                _join_path(directory, basename) for basename in basenames if storage.exists(_join_path(directory, basename))
            )
            continue
        existing.update(_join_path(directory, basename) for basename in basenames.intersection(listed))
    return existing


class Command(BaseCommand):
    help = 'Report media files that are missing from storage or shared by more than one object'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            '--include-renditions',
            action='store_true',
            help='Also check image renditions (these can be regenerated as long as the original exists)',
        )

    def handle(self, *args, **options) -> None:
        models: list[type[Model]] = [AplansImage, AplansDocument]
        if options['include_renditions']:
            models.append(AplansRendition)

        problem_count = 0
        for model in models:
            problem_count += self.report_shared_files(model)
            problem_count += self.report_missing_files(model)

        if problem_count:
            raise CommandError(f'Found {problem_count} problem(s)')
        self.stdout.write(self.style.SUCCESS('No problems found'))

    def report_shared_files(self, model: type[Model]) -> int:
        """
        Report files that more than one object points at.

        Such objects are a time bomb: deleting any one of them takes the file away from the others.
        """
        manager = model._default_manager
        shared = manager.exclude(file='').values('file').annotate(count=Count('pk')).filter(count__gt=1)
        problem_count = 0
        for row in shared.order_by('-count', 'file'):
            pks = sorted(manager.filter(file=row['file']).values_list('pk', flat=True))
            self.stderr.write(
                self.style.WARNING(f'{model.__name__}: file {row["file"]!r} is shared by {row["count"]} objects: {pks}')
            )
            problem_count += 1
        return problem_count

    def report_missing_files(self, model: type[Model]) -> int:
        manager = model._default_manager
        names_by_pk: dict[object, str] = dict(manager.exclude(file='').values_list('pk', 'file'))
        if not names_by_pk:
            return 0

        file_field = model._meta.get_field('file')
        assert isinstance(file_field, FileField)
        existing = _existing_names(file_field.storage, set(names_by_pk.values()))
        missing = {pk: name for pk, name in names_by_pk.items() if name not in existing}
        for pk, name in sorted(missing.items(), key=lambda item: str(item[0])):
            self.stderr.write(self.style.ERROR(f'{model.__name__} {pk}: file {name!r} is missing from storage'))
        return len(missing)
