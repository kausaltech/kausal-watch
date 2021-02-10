from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from wagtail.admin.edit_handlers import FieldPanel, InlinePanel
from wagtail.admin.menu import Menu, MenuItem, SubmenuMenuItem
from wagtail.contrib.modeladmin.options import ModelAdmin, modeladmin_register
from wagtail.core import hooks
from wagtail.images.edit_handlers import ImageChooserPanel

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
        _('Choose plan'), plan_chooser, classnames='icon icon-fa-check-circle-o', order=9000
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


class OwnIndicatorsPanel:
    name = 'own_indicators'
    order = 11

    def __init__(self, request):
        self.request = request

    def render(self):
        user = self.request.user
        plan = user.get_active_admin_plan()
        own_indicators = plan.indicators.filter(contact_persons__person__user=user).distinct()
        return render_to_string('aplans_admin/own_indicators_panel.html', {
            'own_indicators': own_indicators,
        }, request=self.request)


@hooks.register('construct_homepage_panels')
def construct_homepage_panels(request, panels):
    panels.insert(0, OwnActionsPanel(request))
    panels.insert(1, OwnIndicatorsPanel(request))


class ClientAdmin(ModelAdmin):
    model = Client
    menu_icon = 'fa-bank'  # change as required
    menu_order = 500  # will put in 3rd place (000 being 1st, 100 2nd)
    list_display = ('name',)
    search_fields = ('name',)

    panels = [
        FieldPanel('name'),
        ImageChooserPanel('logo'),
        FieldPanel('azure_ad_tenant_id'),
        FieldPanel('login_header_text'),
        FieldPanel('login_button_text'),
        InlinePanel('admin_hostnames', panels=[FieldPanel('hostname')], heading=_('Admin hostnames')),
        InlinePanel('email_domains', panels=[FieldPanel('domain')], heading=_('Email domains')),
        InlinePanel('plans', panels=[FieldPanel('plan')], heading=_('Plans')),
    ]


modeladmin_register(ClientAdmin)


@hooks.register("insert_global_admin_css", order=900)
def global_admin_css():
    return format_html(
        '<link rel="stylesheet" href="{}">',
        static("css/wagtail_admin_overrides.css")
    )


@hooks.register("insert_editor_css", order=900)
def editor_css():
    return format_html(
        '<link rel="stylesheet" href="{}">',
        static("css/wagtail_editor_overrides.css")
    )


@hooks.register("construct_explorer_page_queryset")
def restrict_pages_to_plan(parent_page, pages, request):
    plan = request.user.get_active_admin_plan()
    if not plan.site_id:
        return pages.none()
    return pages.descendant_of(plan.site.root_page, inclusive=True)


@hooks.register("construct_page_chooser_queryset")
def restrict_chooser_pages_to_plan(pages, request):
    plan = request.user.get_active_admin_plan()
    if not plan.site_id:
        return pages.none()
    return pages.descendant_of(plan.site.root_page, inclusive=True)


@hooks.register('construct_page_action_menu')
def reorder_page_action_menu_items(menu_items, request, context):
    for index, item in enumerate(menu_items):
        if item.name == 'action-publish':
            menu_items.pop(index)
            menu_items.insert(0, item)
            break
