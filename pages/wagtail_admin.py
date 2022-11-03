from django.utils.translation import gettext_lazy as _
from wagtail.core import hooks
from wagtail.core.models import PagePermissionTester


class VeryRestrictivePagePermissionTester(PagePermissionTester):
    def can_copy(self):
        return False

    def can_delete(self, ignore_bulk=False):
        return False

    def can_unpublish(self):
        return False


@hooks.register('construct_page_listing_buttons')
def restrict_more_button_permissions_very_much(buttons, page, page_perms, is_parent=False, context=None):
    if getattr(page, 'restrict_more_button_permissions_very_much', False):
        for button in buttons:
            if button.label == _("More"):
                button.page_perms = VeryRestrictivePagePermissionTester(page_perms.user_perms, page_perms.page)


@hooks.register('construct_page_action_menu')
def remove_page_action_menu_items_except_publish(menu_items, request, context):
    if getattr(context.get('page'), 'remove_page_action_menu_items_except_publish', False):
        menu_items[:] = [i for i in menu_items if i.__class__.__name__ == 'PublishMenuItem']
