from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


def remove_from_staff_if_no_plan_admin(user, **kwargs):
    if not user.get_adminable_plans():
        user.is_staff = False
        user.save()


# Not necessary with Wagtail 4?
# def remove_default_site_summary_items(hooks):
#     # Wagtail shows the number of pages, images and documents in the default summary
#     # panel with no option to prevent it. Monkeypatch them away.
#     from wagtail.documents.wagtail_hooks import add_documents_summary_item
#     from wagtail.images.wagtail_hooks import add_images_summary_item
#     from wagtail.admin.wagtail_hooks import add_pages_summary_item
#     from wagtailsvg.wagtail_hooks import add_svg_summary_item
#
#     hooks_to_remove = [
#         add_documents_summary_item, add_images_summary_item, add_pages_summary_item, add_svg_summary_item
#     ]
#     summary_hooks = hooks.get_hooks('construct_homepage_summary_items')
#     for item in summary_hooks:
#         if item in hooks_to_remove:
#             summary_hooks.remove(item)


def remove_user_related_menu_items(hooks):
    from wagtail.admin import wagtail_hooks  # noqa
    from wagtail.admin.views.account import AvatarSettingsPanel
    from wagtail.admin.wagtail_hooks import register_reports_menu

    AvatarSettingsPanel.is_active = lambda self: False

    menu_item_hooks = hooks.get_hooks('register_admin_menu_item')
    for idx, val in enumerate(menu_item_hooks):
        if val == register_reports_menu:
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
