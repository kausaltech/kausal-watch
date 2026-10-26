from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = 'documents'

    def ready(self):
        # monkeypatch filtering of Collections
        from .chooser import monkeypatch_chooser

        monkeypatch_chooser()

        # Don't let deleting one document delete a file that another document still points at.
        from aplans.media_cleanup import ensure_file_cleanup_guard_installed

        ensure_file_cleanup_guard_installed()
