from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = 'documents'

    def ready(self):
        # monkeypatch filtering of Collections
        from .chooser import monkeypatch_chooser
        monkeypatch_chooser()

        from wagtail.documents import wagtail_hooks  # noqa
        from .rich_text import DocumentLinkHandler  # noqa
