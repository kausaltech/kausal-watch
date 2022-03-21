import django.apps
from django.apps import AppConfig

# from .conf import check_fallback_chain
from .translator import translate_model


# class RegistrationConfig(AppConfig):
class I18nConfig(AppConfig):
    # name = "modeltrans"
    name = 'i18n'
    # verbose_name = "Django modeltrans using a registry."

    def ready(self):
        # Deactivated (BB)
        # check_fallback_chain()

        for Model in django.apps.apps.get_models():
            translate_model(Model)
