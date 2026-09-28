from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wagtail.blocks.stream_block import StreamValue
    from wagtail.models import Page

    from pages.models import ActionListPage
    from reports.models import ReportType


# ActionListPage fields whose stream blocks may contain a `report_comparison` block
REPORT_COMPARISON_FIELDS = ('details_main_top', 'details_main_bottom')


@dataclass
class ReportTypeUsage:
    """Where a report type is used, and what deleting it would take along."""

    pages: list[ActionListPage] = field(default_factory=list)
    """Pages whose current content has a report comparison block for the report type."""

    draft_pages: list[ActionListPage] = field(default_factory=list)
    """Pages whose unpublished draft has a report comparison block for the report type."""

    report_count: int = 0
    snapshot_count: int = 0

    @property
    def blocks_deletion(self) -> bool:
        return bool(self.pages or self.draft_pages)


def _stream_references_report_type(stream_value: StreamValue | None, report_type: ReportType) -> bool:
    if not stream_value:
        return False
    for child in stream_value:
        if child.block_type != 'report_comparison':
            continue
        referenced = child.value.get('report_type')
        if referenced is not None and referenced.pk == report_type.pk:
            return True
    return False


def page_references_report_type(page: ActionListPage, report_type: ReportType) -> bool:
    return any(_stream_references_report_type(getattr(page, field_name), report_type) for field_name in REPORT_COMPARISON_FIELDS)


def get_report_type_usage(report_type: ReportType) -> ReportTypeUsage:
    from pages.models import ActionListPage
    from reports.models import ActionSnapshot, Report

    usage = ReportTypeUsage(
        report_count=Report.objects.filter(type=report_type).count(),
        snapshot_count=ActionSnapshot.objects.filter(report__type=report_type).count(),
    )

    # The report type chooser only offers report types of the active plan, so only the plan's own pages (in any
    # of its languages) can refer to it.
    plan = report_type.plan
    if plan.site_id is None:
        return usage
    for root in plan.root_page.get_translations(inclusive=True):
        for page in root.get_descendants().type(ActionListPage).specific():
            _add_page_usage(usage, page, report_type)
    return usage


def _add_page_usage(usage: ReportTypeUsage, page: Page, report_type: ReportType) -> None:
    from pages.models import ActionListPage

    assert isinstance(page, ActionListPage)
    if page_references_report_type(page, report_type):
        usage.pages.append(page)
    if not page.has_unpublished_changes or page.latest_revision is None:
        return
    draft = page.latest_revision.as_object()
    assert isinstance(draft, ActionListPage)
    if page_references_report_type(draft, report_type):
        usage.draft_pages.append(page)
