from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


def remove_default_site_summary_items(hooks):
    # Wagtail shows the number of pages, images and documents in the default summary
    # panel with no option to prevent it. Monkeypatch them away.
    from wagtail.documents.wagtail_hooks import add_documents_summary_item
    from wagtail.images.wagtail_hooks import add_images_summary_item
    from wagtail.admin.wagtail_hooks import add_pages_summary_item

    summary_hooks = hooks._hooks['construct_homepage_summary_items']
    for item in list(summary_hooks):
        if item[0] in (add_documents_summary_item, add_images_summary_item, add_pages_summary_item):
            summary_hooks.remove(item)


def remove_user_related_menu_items(hooks):
    from wagtail.admin import wagtail_hooks  # noqa
    from wagtail.admin.wagtail_hooks import register_reports_menu

    account_hooks = hooks._hooks['register_account_menu_item']
    for idx, val in enumerate(account_hooks):
        if val[0] == wagtail_hooks.register_account_set_profile_picture:
            break
    else:
        val = None
    if val is not None:
        account_hooks.remove(val)

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
        from wagtail.core import hooks

        user_logged_in.connect(create_permissions)
        remove_user_related_menu_items(hooks)
        remove_default_site_summary_items(hooks)
