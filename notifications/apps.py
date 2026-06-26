from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NotificationsConfig(AppConfig):
    name = 'notifications'
    verbose_name = _('Notifications')

    def ready(self) -> None:
        from django.core.checks import register

        from .checks import check_admin_base_url

        register(check_admin_base_url, deploy=True)
