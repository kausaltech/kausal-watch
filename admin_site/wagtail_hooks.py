from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from wagtail.core import hooks
from wagtail.admin.menu import Menu, MenuItem, SubmenuMenuItem
from actions.models import Plan


class PlanChooserMenuItem(SubmenuMenuItem):
    def is_shown(self, request):
        if len(self.menu.menu_items_for_request(request)) > 1:
            return True
        return False

    def is_active(self, request):
        return bool(self.menu.active_menu_items(request))


class PlanItem(MenuItem):
    pass


class PlanChooserMenu(Menu):
    def menu_items_for_request(self, request):
        user = request.user
        plans = user.get_adminable_plans()
        items = []
        for plan in plans:
            url = reverse('change-admin-plan', kwargs=dict(plan_id=plan.id))
            url += '?admin=wagtail'
            item = PlanItem(plan.name, url)
            items.append(item)
        return items


plan_chooser = PlanChooserMenu(None)


@hooks.register('register_admin_menu_item')
def register_plan_chooser():
    return PlanChooserMenuItem(
        _('Choose plan'), plan_chooser, classnames='icon icon-site', order=9000
    )
