from django.apps import AppConfig


class ImagesConfig(AppConfig):
    name = 'images'

    def ready(self):
        # monkeypatch filtering of Collections
        from .chooser import monkeypatch_chooser
        monkeypatch_chooser()

        from wagtail.images import permissions

        # Register graphql types overrides for grapple
        from . import schema  # noqa: F401

        # monkeypatch new permission policy
        from .permissions import permission_policy
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
