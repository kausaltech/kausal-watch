from django.apps import AppConfig


class ImagesConfig(AppConfig):
    name = 'images'

    def ready(self):
        # monkeypatch filtering of Collections
        from .chooser import monkeypatch_chooser
        monkeypatch_chooser()

        # Register feature detection library
        from willow.registry import registry
        import rustface.willow

        registry.register_plugin(rustface.willow)
