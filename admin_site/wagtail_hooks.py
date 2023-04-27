from typing import Any
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from wagtail.admin.edit_handlers import FieldPanel, InlinePanel
from wagtail.admin.menu import Menu, MenuItem, SubmenuMenuItem
from wagtail.admin.ui.components import Component
from wagtail.contrib.modeladmin.options import ModelAdmin, modeladmin_register
from wagtail import hooks
from wagtail.images.edit_handlers import ImageChooserPanel

from aplans.types import WatchAdminRequest

from .models import Client
from actions.models import CommonCategoryType


# FIXME: Refactor duplicated code for categories, common categories, attribute types and reports
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


class CommonCategoryMenuItem(MenuItem):
    def __init__(self, common_category_type, **kwargs):
        self.common_category_type = common_category_type
        self.base_url = reverse('actions_commoncategory_modeladmin_index')
        url = f'{self.base_url}?common_category_type={common_category_type.id}'
        label = common_category_type.name
        super().__init__(label, url, **kwargs)

    def is_active(self, request):
        path, _ = self.url.split('?', maxsplit=1)
        common_category_type = request.GET.get('common_category_type')
        return request.path.startswith(self.base_url) and common_category_type == str(self.common_category_type.pk)


class CommonCategoryMenu(Menu):
    def menu_items_for_request(self, request):
        if request.user.is_superuser:
            return [CommonCategoryMenuItem(cct) for cct in CommonCategoryType.objects.all()]
        return []


common_category_menu = CommonCategoryMenu(None)


@hooks.register('register_admin_menu_item')
def register_common_category_menu():
    return SubmenuMenuItem(
        _('Common categories'),
        common_category_menu,
        classnames='icon icon-folder-open-inverse',
        order=110
    )


class AttributeTypeMenuItem(MenuItem):
    def __init__(self, content_type, **kwargs):
        self.content_type = content_type
        self.base_url = reverse('actions_attributetype_modeladmin_index')
        url = f'{self.base_url}?content_type={content_type.id}'
        label = capfirst(content_type.model_class()._meta.verbose_name)
        super().__init__(label, url, **kwargs)

    def is_active(self, request):
        path, _ = self.url.split('?', maxsplit=1)
        content_type = request.GET.get('content_type')
        return request.path.startswith(self.base_url) and content_type == str(self.content_type.pk)


class AttributeTypeMenu(Menu):
    def menu_items_for_request(self, request):
        user = request.user
        plan = user.get_active_admin_plan()
        items = []
        if user.is_general_admin_for_plan(plan):
            action_ct = ContentType.objects.get(app_label='actions', model='action')
            category_ct = ContentType.objects.get(app_label='actions', model='category')
            items.append(AttributeTypeMenuItem(action_ct))
            items.append(AttributeTypeMenuItem(category_ct))
        return items


attribute_type_menu = AttributeTypeMenu(None)


@hooks.register('register_admin_menu_item')
def register_attribute_type_menu():
    return SubmenuMenuItem(
        _('Attributes'),
        attribute_type_menu,
        classnames='icon icon-tag',
        order=120,
    )


class ReportMenuItem(MenuItem):
    def __init__(self, report_type, **kwargs):
        self.report_type = report_type
        self.base_url = reverse('reports_report_modeladmin_index')
        url = f'{self.base_url}?report_type={report_type.id}'
        label = report_type.name
        super().__init__(label, url, **kwargs)

    def is_active(self, request):
        path, _ = self.url.split('?', maxsplit=1)
        report_type = request.GET.get('report_type')
        return request.path.startswith(self.base_url) and report_type == str(self.report_type.pk)


class ReportMenu(Menu):
    def menu_items_for_request(self, request):
        user = request.user
        plan = user.get_active_admin_plan()
        items = []
        # TODO: Enable for general admins when ready
        # if user.is_general_admin_for_plan(plan):
        if user.is_superuser:
            for report_type in plan.report_types.all():
                item = ReportMenuItem(report_type)
                items.append(item)
        return items


report_menu = ReportMenu(None)


@hooks.register('register_admin_menu_item')
def register_report_menu():
    return SubmenuMenuItem(
        _('Reports'),
        report_menu,
        classnames='icon icon-doc-full',
        order=130
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


class OwnIndicatorsPanel(Component):
    name = 'own_indicators'
    order = 102
    template_name = 'aplans_admin/own_indicators_panel.html'

    def get_context_data(self, parent_context: dict[str, Any]) -> dict[str, Any]:
        request: WatchAdminRequest = parent_context['request']
        ctx = super().get_context_data(parent_context)
        user = request.user
        plan = request.get_active_admin_plan()
        ctx['own_indicators'] = plan.indicators.filter(contact_persons__person__user=user).distinct()
        return ctx


@hooks.register('construct_homepage_panels')
def construct_homepage_panels(request, panels):
    from wagtail.admin.site_summary import SiteSummaryPanel

    allowed_panels = (SiteSummaryPanel,)
    panels_to_remove = []
    for panel in panels:
        if not isinstance(panel, allowed_panels):
            panels_to_remove.append(panel)
    for panel in panels_to_remove:
        panels.remove(panel)

    panels.insert(1, OwnIndicatorsPanel())


@hooks.register('construct_homepage_summary_items', order=1000)
def remove_default_site_summary_items(request, items: list):
    items.clear()


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
        FieldPanel('google_login_enabled'),
        FieldPanel('google_login_button_text'),
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

"""
@hooks.register("insert_editor_css", order=900)
def editor_css():
    return format_html(
        '<link rel="stylesheet" href="{}">',
        static("css/wagtail_editor_overrides.css")
    )
"""

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


@hooks.register('construct_settings_menu')
def remove_settings_menu_items(request, items: list):
    from wagtail.users.wagtail_hooks import (
        GroupsMenuItem, UsersMenuItem
    )
    from wagtail.admin.wagtail_hooks import (
        WorkflowsMenuItem, WorkflowReportMenuItem, WorkflowTasksMenuItem
    )
    from wagtail.sites.wagtail_hooks import (
        SitesMenuItem
    )
    from wagtail.locales.wagtail_hooks import (
        LocalesMenuItem
    )
    from wagtail.contrib.redirects.wagtail_hooks import (
        RedirectsMenuItem
    )

    item_classes_to_remove = (
        GroupsMenuItem, UsersMenuItem,
        WorkflowsMenuItem, WorkflowReportMenuItem, WorkflowTasksMenuItem,
        SitesMenuItem, LocalesMenuItem, RedirectsMenuItem
    )
    to_remove = []
    for item in items:
        if isinstance(item, item_classes_to_remove):
            to_remove.append(item)
    for item in to_remove:
        items.remove(item)
