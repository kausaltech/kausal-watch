from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = 'documents'

    def ready(self):
        # monkeypatch filtering of Collections
        from .chooser import monkeypatch_chooser
        monkeypatch_chooser()

        # monkeypatch new permission policy
        from .permissions import permission_policy
        from wagtail.documents import permissions
        permissions.permission_policy = permission_policy

        from wagtail.documents.forms import BaseDocumentForm
        BaseDocumentForm.permission_policy = permission_policy

        from wagtail.documents import wagtail_hooks  # noqa
        from .rich_text import DocumentLinkHandler  # noqa
