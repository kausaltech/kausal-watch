from django.utils.translation import gettext_lazy as _
from django.urls import reverse
from django.template.loader import render_to_string
from wagtail.core import hooks
from wagtail.admin.edit_handlers import (
    FieldPanel
)
from wagtail.admin.menu import Menu, MenuItem, SubmenuMenuItem
from wagtail.contrib.modeladmin.options import ModelAdmin, modeladmin_register
from actions.models import Plan

from .models import Client


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


class OwnActionsPanel:
    name = 'own_actions'
    order = 10

    def __init__(self, request):
        self.request = request

    def render(self):
        user = self.request.user
        plan = user.get_active_admin_plan()
        own_actions = plan.actions.filter(contact_persons__person__user=user).distinct().order_by('order')
        return render_to_string('aplans_admin/own_actions_panel.html', {
            'own_actions': own_actions,
        }, request=self.request)


@hooks.register('construct_homepage_panels')
def construct_homepage_panels(request, panels):
    panels.insert(0, OwnActionsPanel(request))
    print(panels)


class ClientAdmin(ModelAdmin):
    model = Client
    menu_icon = 'wagtail'  # change as required
    menu_order = 500  # will put in 3rd place (000 being 1st, 100 2nd)
    list_display = ('name',)
    search_fields = ('name',)

    panels = [
        FieldPanel('name'),
        FieldPanel('logo'),
    ]


modeladmin_register(ClientAdmin)
