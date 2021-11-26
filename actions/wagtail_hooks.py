from django.templatetags.static import static
from wagtail.core import hooks
from wagtail.admin.site_summary import SummaryItem

from . import wagtail_admin  # noqa

class ActionsSummaryItem(SummaryItem):
    order = 200
    template = 'site_summary/actions.html'

    def get_context(self):
        plan = self.request.user.get_active_admin_plan()
        return {
            'total_actions': plan.actions.active().count(),
            'plan': plan,
        }

    def is_shown(self):
        return True


@hooks.register('construct_homepage_summary_items')
def add_actions_summary_item(request, items):
    items.append(ActionsSummaryItem(request))


@hooks.register('insert_editor_js')
def editor_js():
    return f'<script src="{static("actions/action-tasks-wagtail.js")}"></script>'
