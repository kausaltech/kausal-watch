from django.apps import AppConfig


class ImagesConfig(AppConfig):
    name = 'images'

    def ready(self):
        # monkeypatch filtering of Collections
        from .chooser import monkeypatch_chooser
        monkeypatch_chooser()

        # monkeypatch new permission policy
        from .permissions import permission_policy
        from wagtail.images import permissions
        permissions.permission_policy = permission_policy

        from wagtail.images.forms import BaseImageForm
        BaseImageForm.permission_policy = permission_policy

        # Register feature detection library
        from willow.registry import registry
        import rustface.willow

        registry.register_plugin(rustface.willow)
