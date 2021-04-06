from django.utils.translation import gettext_lazy as _
from wagtail.core import hooks


@hooks.register('construct_page_listing_buttons')
def remove_page_listing_more_button(buttons, page, page_perms, is_parent=False, context=None):
    if getattr(page, 'remove_page_listing_more_button', False):
        # Remove "More" dropdown button
        buttons[:] = [b for b in buttons if b.label != _("More")]


@hooks.register('construct_page_action_menu')
def remove_page_action_menu_items_except_publish(menu_items, request, context):
    if getattr(context.get('page'), 'remove_page_action_menu_items_except_publish', False):
        menu_items[:] = [i for i in menu_items if i.__class__.__name__ == 'PublishMenuItem']
