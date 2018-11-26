from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ActionsConfig(AppConfig):
    name = 'actions'
    verbose_name = _('Actions')
