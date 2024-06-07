from django.core.files import File
from django.core.files.storage import Storage
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible
from storages.backends.s3boto3 import S3Boto3Storage

@deconstructible
class LocalMediaStorageWithS3Fallback(Storage):
    """Storage that writes everything to disk and reads files from disk, falling back to S3."""
    def __init__(self):
        self.s3_storage = S3Boto3Storage()
        self.fs_storage = FileSystemStorage()

    def _open(self, name: str, mode: str = 'rb') -> File:
        # Since _save() always works on the disk, we don't want to open S3 files for writing. Then again, is _open()
        # actually ever called for anything else but reading?
        assert mode == 'rb'
        try:
            return self.fs_storage._open(name, mode)
        except FileNotFoundError:
            return self.s3_storage._open(name, mode)

    def _save(self, name: str, content: File) -> str:
        return self.fs_storage._save(name, content)

    def path(self, name: str) -> str:
        # The path returned by `self.fs_storage.path(name)` might not exist, so check if it does first
        if not self.fs_storage.exists(name):
            # Wagtail's ImageFileMixin expects NotImplementedError for files that are not stored locally.
            # Alternatively, we could also override `ImageFileMixin.is_stored_locally()` in `AplansImage`,
            # but then we'd have to check there which storage backend is used.
            raise NotImplementedError("File does not exist locally.")
        return self.fs_storage.path(name)

    def delete(self, name: str) -> None:
        if self.fs_storage.exists(name):
            self.fs_storage.delete(name)

    def exists(self, name: str) -> bool:
        return self.fs_storage.exists(name) or self.s3_storage.exists(name)

    def listdir(self, path: str) -> tuple[list[str], list[str]]:
        """Return union of S3 and local files."""
        s3_dirs, s3_files = self.s3_storage.listdir(path)
        fs_dirs, fs_files = self.fs_storage.listdir(path)
        dirs, files = list(s3_dirs), list(s3_files)
        dirs.extend(d for d in fs_dirs if d not in s3_dirs)
        files.extend(f for f in fs_files if f not in s3_files)
        return dirs, files

    def size(self, name: str) -> int:
        if self.fs_storage.exists(name):
            return self.fs_storage.size(name)
        return self.s3_storage.size(name)

    def url(self, name: str) -> str:
        if self.fs_storage.exists(name):
            return self.fs_storage.url(name)
        return self.s3_storage.url(name)
