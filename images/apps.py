from django.apps import AppConfig


class ImagesConfig(AppConfig):
    name = 'images'

    def ready(self):
        # monkeypatch filtering of Collections
        from .chooser import monkeypatch_chooser

        monkeypatch_chooser()

        from wagtail.images import permissions

        # Register custom rich text image embed handler that injects
        # data-image-credit attributes on <img> tags in rich text.
        # We force a feature scan first so that Wagtail's default hooks
        # have already run, then override the 'image' embed type with
        # ours and clear the rewriter cache.
        from wagtail.rich_text import features as rich_text_features, get_rewriter

        # Register graphql types overrides for grapple
        from . import schema  # noqa: F401

        # monkeypatch new permission policy
        from .permissions import permission_policy
        from .rich_text import ImageEmbedHandler

        rich_text_features.get_embed_types()  # ensure scan has completed
        rich_text_features.register_embed_type(ImageEmbedHandler)
        get_rewriter.cache_clear()

        permissions.permission_policy = permission_policy

        from wagtail.images.forms import BaseImageForm

        BaseImageForm.permission_policy = permission_policy

        # Register feature detection library
        from willow.registry import registry

        try:
            import rustface.willow
        except ImportError:
            pass
        else:
            registry.register_plugin(rustface.willow)

        # Remove the bulk delete bulk actions from documents, images
        # because that action is not logged in the audit log
        from wagtail.admin.views.bulk_action.registry import bulk_action_registry

        for app, model in (('documents', 'aplansdocument'), ('images', 'aplansimage')):
            if len(bulk_action_registry.get_bulk_actions_for_model(app, model)):
                bulk_action_registry.actions[app][model] = {
                    k: v for k, v in bulk_action_registry.actions[app][model].items() if k != 'delete'
                }
