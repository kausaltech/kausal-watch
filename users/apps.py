from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    name = 'users'
    verbose_name = _('Users')

    def ready(self):
        from django.contrib.auth import user_logged_in
        from .perms import create_permissions
        from wagtail.admin import wagtail_hooks  # noqa
        from wagtail.core import hooks

        user_logged_in.connect(create_permissions)
        account_hooks = hooks._hooks['register_account_menu_item']
        for idx, val in enumerate(account_hooks):
            if val[0] == wagtail_hooks.register_account_set_profile_picture:
                break
        else:
            val = None
        if val is not None:
            account_hooks.remove(val)

        from wagtail.admin.wagtail_hooks import register_reports_menu
        menu_item_hooks = hooks._hooks['register_admin_menu_item']
        for idx, val in enumerate(menu_item_hooks):
            if val[0] == register_reports_menu:
                break
        else:
            val = None
        if val is not None:
            menu_item_hooks.remove(val)
