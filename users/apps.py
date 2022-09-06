from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


def remove_from_staff_if_no_plan_admin(user, **kwargs):
    if not user.get_adminable_plans():
        user.is_staff = False
        user.save()


def remove_user_related_menu_items(hooks):
    from wagtail.admin import wagtail_hooks  # noqa
    from wagtail.admin.views.account import AvatarSettingsPanel
    from wagtail.admin.wagtail_hooks import register_reports_menu

    AvatarSettingsPanel.is_active = lambda self: False

    menu_item_hooks = hooks._hooks['register_admin_menu_item']
    for idx, val in enumerate(menu_item_hooks):
        if val[0] == register_reports_menu:
            break
    else:
        val = None
    if val is not None:
        menu_item_hooks.remove(val)


class UsersConfig(AppConfig):
    name = 'users'
    verbose_name = _('Users')

    def ready(self):
        from django.contrib.auth import user_logged_in
        from .perms import create_permissions
        from wagtail import hooks

        user_logged_in.connect(create_permissions)
        user_logged_in.connect(remove_from_staff_if_no_plan_admin)
        remove_user_related_menu_items(hooks)
