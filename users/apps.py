from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    name = 'users'
    verbose_name = _('Users')

    def ready(self):
        from django.contrib.auth import user_logged_in
        from .perms import create_permissions

        user_logged_in.connect(create_permissions)
