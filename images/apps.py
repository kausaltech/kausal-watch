from django.apps import AppConfig


class ImagesConfig(AppConfig):
    name = 'images'

    def ready(self):
        # monkeypatch filtering of Collections
        from .chooser import monkeypatch_chooser
        monkeypatch_chooser()

        # monkeypatch new permission policy
        from wagtail.images import permissions

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
