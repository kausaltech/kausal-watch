from typing import Mapping, Any

from wagtail import hooks
from wagtail.admin.site_summary import SummaryItem

from aplans.types import WatchAdminRequest

from . import wagtail_admin  # noqa


class IndicatorsSummaryItem(SummaryItem):
    template_name = 'site_summary/indicators.html'
    request: WatchAdminRequest

    def get_context_data(self, parent_context: Mapping[str, Any]) -> Mapping[str, Any]:
        ctx = super().get_context_data(parent_context)
        plan = self.request.get_active_admin_plan()
        ctx['total_indicators'] = plan.indicators.count()
        ctx['plan'] = plan
        return ctx

    def is_shown(self):
        return True


@hooks.register('construct_homepage_summary_items', order=1001)
def add_indicators_summary_item(request, items):
    items.append(IndicatorsSummaryItem(request))
