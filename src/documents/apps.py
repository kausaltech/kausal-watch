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

        # monkeypatch new permission policy
        from wagtail.documents import permissions

        from .permissions import permission_policy

        permissions.permission_policy = permission_policy

        from wagtail.documents.forms import BaseDocumentForm

        BaseDocumentForm.permission_policy = permission_policy

        from wagtail.documents.views.chooser import viewset

        viewset.permission_policy = permission_policy

        import wagtail.documents.wagtail_hooks  # noqa: F401

        from .rich_text import DocumentLinkHandler  # noqa: F401
