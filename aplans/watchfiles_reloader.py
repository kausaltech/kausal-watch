from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from django.utils import autoreload

import watchfiles  # type: ignore

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence


class DjangoPythonFilter(watchfiles.PythonFilter):
    ignore_dirs: Sequence[str]

    def __init__(self, *, ignore_paths: Sequence[str | Path] | None = None, extra_extensions: Sequence[str] = ()) -> None:
        dirs = list(self.ignore_dirs)

        for dirname in ('site-packages', '.venv'):
            # We want to watch site-packages, too
            if dirname in dirs:
                dirs.remove(dirname)

        self.ignore_dirs = dirs
        super().__init__(ignore_paths=ignore_paths, extra_extensions=extra_extensions)


class WatchfilesReloader(autoreload.BaseReloader):
    def watched_roots(self, watched_files: list[Path]) -> frozenset[Path]:
        extra_directories = self.directory_globs.keys()
        watched_file_dirs = {f.parent for f in watched_files}
        sys_paths = set(autoreload.sys_path_directories())
        return frozenset((*extra_directories, *watched_file_dirs, *sys_paths))

    def tick(self) -> Generator[None]:
        watched_files = list(self.watched_files(include_globs=False))
        watched_roots = self.watched_roots(watched_files)
        roots = autoreload.common_roots(watched_roots)
        # Watch Python files plus template files (HTML, Jinja2, text templates for emails)
        watcher = watchfiles.watch(
            *roots,
            watch_filter=DjangoPythonFilter(extra_extensions=('html', 'jinja2', 'txt'))
        )
        for file_changes in watcher:
            for _, path in file_changes:
                self.notify_file_changed(Path(path))
            yield


def replaced_get_reloader() -> autoreload.BaseReloader:
    return WatchfilesReloader()


def replace_reloader():
    autoreload.get_reloader = replaced_get_reloader
