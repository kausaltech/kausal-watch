from __future__ import annotations

from typing import TYPE_CHECKING

from django.templatetags.static import static
from wagtail import hooks
from wagtail.admin.site_summary import SummaryItem

from admin_site.wagtail import execute_admin_post_save_tasks

from . import wagtail_admin  # noqa: F401

if TYPE_CHECKING:
    from laces.typing import RenderContext

    from aplans.types import WatchAdminRequest


class ActionsSummaryItem(SummaryItem):
    template_name = 'site_summary/actions.html'
    request: WatchAdminRequest

    def get_context_data(self, parent_context: RenderContext) -> RenderContext:
        ctx = super().get_context_data(parent_context)
        assert ctx is not None
        plan = self.request.get_active_admin_plan()
        ctx['active_actions'] = plan.actions.get_queryset().active().count()
        ctx['plan'] = plan
        return ctx

    def is_shown(self):
        return True


@hooks.register('construct_homepage_summary_items', order=1001)
def add_actions_summary_item(request, items):
    items.append(ActionsSummaryItem(request))


@hooks.register('insert_editor_js')
def editor_js():
    return f'<script src="{static("actions/action-tasks-wagtail.js")}"></script>'


@hooks.register('after_edit_snippet')
def after_edit_snippet(request, snippet):
    execute_admin_post_save_tasks(snippet, request.user)
