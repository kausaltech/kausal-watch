from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class IndicatorsConfig(AppConfig):
    name = 'indicators'
    verbose_name = _('Indicators')

    def ready(self) -> None:
        super().ready()
        from indicators.search_indexing import install_search_auto_update_guard

        install_search_auto_update_guard()
