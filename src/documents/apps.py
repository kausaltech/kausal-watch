from django.apps import AppConfig


class DocumentsConfig(AppConfig):
    name = 'documents'

    def ready(self):
        from wagtail.documents import permissions
        from wagtail.documents.forms import BaseDocumentForm

        from .permissions import permission_policy

        # Install before importing consumers that retain the policy.
        permissions.permission_policy = permission_policy
        BaseDocumentForm.permission_policy = permission_policy

        # monkeypatch filtering of Collections
        from .chooser import monkeypatch_chooser

        monkeypatch_chooser()

        # Don't let deleting one document delete a file that another document still points at.
        from aplans.media_cleanup import ensure_file_cleanup_guard_installed

        ensure_file_cleanup_guard_installed()

        from wagtail.documents.views import chooser

        # Page model imports reach this module through Grapple's StreamField
        # types before ready() runs. Repair those already-captured references.
        chooser.permission_policy = permission_policy
        chooser.DocumentChooserViewSet.permission_policy = permission_policy
        chooser.viewset.permission_policy = permission_policy

        import wagtail.documents.wagtail_hooks  # noqa: F401

        from .rich_text import DocumentLinkHandler  # noqa: F401
