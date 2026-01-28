from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models import Q
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import DismissibleMenuItem, Menu, MenuItem, SubmenuMenuItem
from wagtail.admin.panels import FieldPanel, InlinePanel
from wagtail.admin.ui.components import Component
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from kausal_common.users import user_or_bust

from aplans.context_vars import get_admin_cache

from actions.models import CommonCategoryType

from .models import Client

if TYPE_CHECKING:
    from collections.abc import Sequence

    from laces.typing import RenderContext

    from aplans.types import WatchAdminRequest


# FIXME: Refactor duplicated code for categories, common categories, attribute types and reports
class CategoryMenuItem(MenuItem):
    def __init__(self, category_type, **kwargs):
        self.category_type = category_type
        self.base_url = reverse('actions_category_modeladmin_index')
        url = f'{self.base_url}?category_type={category_type.id}'
        label = category_type.name
        super().__init__(label, url, icon_name='kausal-category', **kwargs)

    def is_active(self, request):
        category_type = request.GET.get('category_type')
        return request.path.startswith(self.base_url) and category_type == str(self.category_type.pk)


class CategoryMenu(Menu):
    def menu_items_for_request(self, request):
        user = user_or_bust(request.user)
        cache = get_admin_cache(request)
        plan = cache.plan
        items = []
        if user.is_general_admin_for_plan(plan):
            for category_type in cache.category_types:
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
        user = user_or_bust(request.user)
        if user.is_superuser:
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
        self.base_url = reverse('plan_reports_report_modeladmin_index')
        url = f'{self.base_url}?report_type={report_type.id}'
        label = report_type.name
        super().__init__(label, url, **kwargs)

    def is_active(self, request):
        report_type = request.GET.get('report_type')
        return request.path.startswith(self.base_url) and report_type == str(self.report_type.pk)


class ReportMenu(Menu):
    def menu_items_for_request(self, request):
        user = user_or_bust(request.user)
        cache = get_admin_cache(request)
        plan = cache.plan
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
        order=40,
        icon_name='doc-full',
    )


class OwnIndicatorsPanel(Component):
    name = 'own_indicators'
    order = 102
    template_name = 'admin_site/own_indicators_panel.html'

    def get_context_data(self, parent_context: RenderContext) -> RenderContext:  # type: ignore[override]
        request: WatchAdminRequest = parent_context['request']
        ctx = super().get_context_data(parent_context)
        assert ctx is not None
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
def remove_default_site_summary_items(request, items: list[MenuItem]):
    items.clear()


class ClientViewSet(SnippetViewSet):
    model = Client
    icon = 'globe'
    menu_order = 520
    list_display = ('name',)
    search_fields = ('name',)
    add_to_admin_menu = True

    panels = [
        FieldPanel('name'),
        FieldPanel('logo'),
        FieldPanel('auth_backend'),
        InlinePanel('email_domains', panels=[FieldPanel('domain')], heading=_('Email domains')),
        InlinePanel('plans', panels=[FieldPanel('plan')], heading=_('Plans')),
    ]


register_snippet(ClientViewSet)


@hooks.register("insert_global_admin_css")
def global_admin_css():
    return format_html(
        '<link rel="stylesheet" href="{}">',
        static("css/admin-styles.css"),
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
    for page in plan.documentation_root_pages.all():
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


def remove_menu_items(
    items: list[MenuItem], item_classes_to_remove: tuple[type, ...] = (), names_to_remove: Sequence[str] | None = None
):
    def should_remove(item: MenuItem) -> bool:
        if isinstance(item, item_classes_to_remove):
            return True
        if names_to_remove and item.name in names_to_remove:
            return True
        return False
    to_remove = []
    for item in items:
        if should_remove(item):
            to_remove.append(item)  # noqa: PERF401
    for item in to_remove:
        items.remove(item)


@hooks.register('construct_settings_menu')
def remove_settings_menu_items(request, items: list[MenuItem]):
    from wagtail.contrib.redirects.wagtail_hooks import (
        RedirectsMenuItem,
    )
    from wagtail.locales.wagtail_hooks import (
        LocalesMenuItem,
    )
    from wagtail.sites.wagtail_hooks import (
        SitesMenuItem,
    )

    item_classes_to_remove = (
        SitesMenuItem, LocalesMenuItem, RedirectsMenuItem,
    )
    names_to_remove = ('users', 'groups')
    remove_menu_items(items, item_classes_to_remove, names_to_remove)


@hooks.register('construct_main_menu')
def remove_main_menu_items(request, items: list[MenuItem]):
    from wagtail.snippets.wagtail_hooks import (
        SnippetsMenuItem,
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
def remove_help_menu_items(request, items: list[MenuItem]):
    items[:] = [item for item in items if not should_remove_help_menu_item(item)]


@hooks.register('construct_help_menu')
def add_documentation_to_help_menu(request, items: list[MenuItem]):
    # Add an item for each documentation page
    plan = request.user.get_active_admin_plan()
    documentation_root = plan.get_translated_documentation_root_page()
    if not documentation_root:
        return
    for page in documentation_root.get_children():
        item = MenuItem(
            label=page.title,
            url=reverse('documentation', kwargs={'page_id': page.id}),
            icon_name='help',
        )
        items.append(item)


@hooks.register("register_icons")
def register_icons(icons):
    basenames = [
        'kausal-action',
        'kausal-attribute',
        'kausal-category',
        'kausal-dimension',
        'kausal-indicator',
        'kausal-organization',
        'kausal-plan',
        'kausal-pledge',
        'kausal-spreadsheet',
        # Icons we copied from Font Awesome have a `fontawesome-` prefix. We also override some icons shipped with
        # Wagtail, but they don't have a prefix even though some of them also come from Font Awesome and they don't need
        # to be registered here.
        # It would be tempting to use `fa-` instead of `fontawesome-`, but the modeladmin package checks in
        # `ModelAdminMenuItem` and `GroupMenuItem` for this hard-coded prefix, and if it's there, it uses
        # CSS-classname-based icons for the menu items. This doesn't work anymore with newer versions of Wagtail.
        'fontawesome-bell',
        'fontawesome-link-slash',
        'fontawesome-rotate-left',
        'fontawesome-chart-line',
        'fontawesome-chart-area',
        'fontawesome-chart-simple',
        'fontawesome-chart-pie',
        'fontawesome-bars-progress',
    ]
    return icons + [f'wagtailadmin/icons/{basename}.svg' for basename in basenames]


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
