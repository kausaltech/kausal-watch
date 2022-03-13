from django.db.models import Q
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


class CategoryMenuItem(MenuItem):
    def __init__(self, category_type, **kwargs):
        self.category_type = category_type
        self.base_url = reverse('actions_category_modeladmin_index')
        url = f'{self.base_url}?category_type={category_type.id}'
        label = category_type.name
        super().__init__(label, url, **kwargs)

    def is_active(self, request):
        path, _ = self.url.split('?', maxsplit=1)
        category_type = request.GET.get('category_type')
        return request.path.startswith(self.base_url) and category_type == str(self.category_type.pk)


class CategoryMenu(Menu):
    def menu_items_for_request(self, request):
        user = request.user
        plan = user.get_active_admin_plan()
        items = []
        if user.is_general_admin_for_plan(plan):
            for category_type in plan.category_types.all():
                item = CategoryMenuItem(category_type)
                items.append(item)
        return items


category_menu = CategoryMenu(None)


@hooks.register('register_admin_menu_item')
def register_category_menu():
    return SubmenuMenuItem(
        _('Categories'),
        category_menu,
        classnames='icon icon-folder-open-inverse',
        order=100
    )


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
            icon_name = ''
            if plan == user.get_active_admin_plan():
                icon_name = 'tick'
            item = PlanItem(plan.name, url, icon_name=icon_name)
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


@hooks.register("insert_global_admin_css", order=0)
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
    # Let's assume the global root node is also part of the plan since we want it to be an explorable page
    q = Q(depth=1)
    for page in plan.root_page.get_translations(inclusive=True):
        q |= pages.descendant_of_q(page, inclusive=True)
    return pages.filter(q)


@hooks.register("construct_page_chooser_queryset")
def restrict_chooser_pages_to_plan(pages, request):
    plan = request.user.get_active_admin_plan()
    if not plan.site_id:
        return pages.none()
    q = pages.descendant_of_q(plan.root_page, inclusive=True)
    for translation in plan.root_page.get_translations():
        q |= pages.descendant_of_q(translation, inclusive=True)
    return pages.filter(q)


@hooks.register('construct_page_action_menu')
def reorder_page_action_menu_items(menu_items, request, context):
    for index, item in enumerate(menu_items):
        if item.name == 'action-publish':
            menu_items.pop(index)
            menu_items.insert(0, item)
            break


@hooks.register('register_rich_text_features')
def enable_superscript_feature(features):
    features.default_features.append('superscript')
    features.default_features.append('subscript')
