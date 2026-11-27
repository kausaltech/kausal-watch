from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.templatetags.static import static
from django.urls import path, reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.ui.sidebar import LinkMenuItem as LinkMenuItemComponent

from kausal_common.users import user_or_bust
from kausal_common.views.types import Component

from . import wagtail_admin as wagtail_admin  # noqa: PLC0414
from .inbox_views import (
    InboxView,
    inbox_enabled,
    mark_all_read_view,
    open_view,
    unread_count,
    unread_count_view,
    unread_label,
)

if TYPE_CHECKING:
    from django.http import HttpRequest

    from laces.typing import RenderContext


@hooks.register('register_admin_urls')
def register_inbox_urls():
    return [
        path('inbox/', InboxView.as_view(), name='notifications_inbox'),
        path('inbox/unread-count/', unread_count_view, name='notifications_inbox_unread_count'),
        path('inbox/<int:pk>/open/', open_view, name='notifications_inbox_open'),
        path('inbox/mark-all-read/', mark_all_read_view, name='notifications_inbox_mark_all_read'),
    ]


class InboxMenuItem(MenuItem):
    def is_shown(self, request: HttpRequest) -> bool:
        return inbox_enabled()

    def render_component(self, request: HttpRequest) -> LinkMenuItemComponent:
        count = unread_count(user_or_bust(request.user))
        attrs = {**self.attrs, 'data-inbox-link': '', 'data-inbox-count-url': reverse('notifications_inbox_unread_count')}
        if count:
            attrs['data-inbox-unread'] = ''
            attrs['title'] = unread_label(count)
        return LinkMenuItemComponent(
            self.name, self.label, self.url, icon_name=self.icon_name, classname=self.classname, attrs=attrs
        )


@hooks.register('register_admin_menu_item')
def register_inbox_menu_item():
    return InboxMenuItem(_('Inbox'), reverse('notifications_inbox'), icon_name='fontawesome-bell', order=1)


@hooks.register('insert_global_admin_js')
def inbox_js():
    if not inbox_enabled():
        return ''
    return format_html('<script src="{}" defer></script>', static('notifications/js/inbox.js'))


@hooks.register('insert_global_admin_css')
def inbox_css():
    if not inbox_enabled():
        return ''
    return format_html('<link rel="stylesheet" href="{}">', static('notifications/css/inbox.css'))


class UnreadNotificationsPanel(Component):
    name = 'unread_notifications'
    order = 50
    template_name = 'notifications/unread_panel.html'

    def __init__(self, count: int):
        self.count = count

    def get_context_data(self, parent_context: RenderContext) -> RenderContext:  # type: ignore[override]
        ctx: dict[str, Any] = dict(super().get_context_data(parent_context) or {})
        ctx['label'] = unread_label(self.count)
        ctx['inbox_url'] = reverse('notifications_inbox')
        return ctx


# Runs after the admin site's own hook, which removes every panel it does not know.
@hooks.register('construct_homepage_panels', order=500)
def add_unread_notifications_panel(request: HttpRequest, panels: list[Component]) -> None:
    if not inbox_enabled():
        return
    count = unread_count(user_or_bust(request.user))
    if count:
        panels.append(UnreadNotificationsPanel(count))
