from typing import Any
from django.db.models import Q
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, InlinePanel
from wagtail.admin.menu import AdminOnlyMenuItem, DismissibleMenuItem, Menu, MenuItem, SubmenuMenuItem
from wagtail.admin.ui.components import Component
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet
from wagtail_modeladmin.options import ModelAdmin, modeladmin_register
from wagtail import hooks

from aplans.types import WatchAdminRequest

from .models import Client
from actions.models import CommonCategoryType
from actions.wagtail_admin import PlanAdmin


# FIXME: Refactor duplicated code for categories, common categories, attribute types and reports
class CategoryMenuItem(MenuItem):
    def __init__(self, category_type, **kwargs):
        self.category_type = category_type
        self.base_url = reverse('actions_category_modeladmin_index')
        url = f'{self.base_url}?category_type={category_type.id}'
        label = category_type.name
        super().__init__(label, url, icon_name='kausal-category', **kwargs)

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
        icon_name='kausal-category',
        order=30,
    )


class CommonCategoryMenuItem(MenuItem):
    def __init__(self, common_category_type, **kwargs):
        self.common_category_type = common_category_type
        self.base_url = reverse('actions_commoncategory_modeladmin_index')
        url = f'{self.base_url}?common_category_type={common_category_type.id}'
        label = common_category_type.name
        super().__init__(label, url, icon_name='kausal-category', **kwargs)

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
        icon_name='kausal-category',
        order=40,
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
        if user.is_general_admin_for_plan(plan):
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
        order=40
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
        url_helper = PlanAdmin().url_helper
        if request.user.is_superuser:
            items.append(AdminOnlyMenuItem(
                _('Create plan'),
                url_helper.get_action_url('create'),
                icon_name='plus-inverse',
                #order=9100,
            ))
        return items


plan_chooser = PlanChooserMenu(None)


@hooks.register('register_admin_menu_item')
def register_plan_chooser():
    return PlanChooserMenuItem(
        _('Choose plan'),
        plan_chooser,
        order=9000,
        icon_name='kausal-plan',
    )


class OwnIndicatorsPanel(Component):
    name = 'own_indicators'
    order = 102
    template_name = 'admin_site/own_indicators_panel.html'

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
    menu_icon = 'globe'
    menu_order = 520
    list_display = ('name',)
    search_fields = ('name',)

    panels = [
        FieldPanel('name'),
        FieldPanel('logo'),
        FieldPanel('auth_backend'),
        InlinePanel('email_domains', panels=[FieldPanel('domain')], heading=_('Email domains')),
        InlinePanel('plans', panels=[FieldPanel('plan')], heading=_('Plans')),
    ]


modeladmin_register(ClientAdmin)


@hooks.register("insert_global_admin_css")
def global_admin_css():
    return format_html(
        '<link rel="stylesheet" href="{}">',
        static("css/admin-styles.css")
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


def remove_menu_items(items, item_classes_to_remove):
    to_remove = []
    for item in items:
        if isinstance(item, item_classes_to_remove):
            to_remove.append(item)
    for item in to_remove:
        items.remove(item)


@hooks.register('construct_settings_menu')
def remove_settings_menu_items(request, items: list):
    from wagtail.users.wagtail_hooks import (
        GroupsMenuItem, UsersMenuItem
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
        GroupsMenuItem, UsersMenuItem, SitesMenuItem, LocalesMenuItem, RedirectsMenuItem
    )
    remove_menu_items(items, item_classes_to_remove)


@hooks.register('construct_main_menu')
def remove_main_menu_items(request, items: list):
    from wagtail.snippets.wagtail_hooks import (
        SnippetsMenuItem
    )

    item_classes_to_remove = (
        SnippetsMenuItem,
    )
    remove_menu_items(items, item_classes_to_remove)


@hooks.register('register_help_menu_item')
def register_video_tutorials_menu_item():
    return DismissibleMenuItem(
        _("Video tutorials"),
        _('https://kausal.gitbook.io/watch'),
        icon_name='help',
        order=1000,
        attrs={"target": "_blank"},
        name='video-tutorials',
    )


def should_remove_help_menu_item(item):
    return (item.name.startswith('whats-new-in-wagtail-')
            or item.name == 'editor-guide')


@hooks.register('construct_help_menu')
def remove_help_menu_items(request, items: list):
    items[:] = [item for item in items if not should_remove_help_menu_item(item)]


@hooks.register("register_icons")
def register_icons(icons):
    return icons + [
        'wagtailadmin/icons/kausal-action.svg',
        'wagtailadmin/icons/kausal-attribute.svg',
        'wagtailadmin/icons/kausal-category.svg',
        'wagtailadmin/icons/kausal-dimension.svg',
        'wagtailadmin/icons/kausal-indicator.svg',
        'wagtailadmin/icons/kausal-organization.svg',
        'wagtailadmin/icons/kausal-plan.svg',
        'wagtailadmin/icons/kausal-spreadsheet.svg',
    ]


@hooks.register('insert_editor_js')
def hack_wagtail_rich_text_fields():
    # Wagtail's rich text editor doesn't care whether its form field is disabled. But it should!
    return mark_safe("""
        <script>
        $(function () {
            const wrapper = $('input[disabled] + * + .Draftail-Editor__wrapper');
            wrapper.find('*').attr('tabindex', '-1');
            wrapper.css('pointer-events', 'none');
            wrapper.parent().css('cursor', 'not-allowed');
        });
        </script>
        """)
