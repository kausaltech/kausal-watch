from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .models import ReportType

if TYPE_CHECKING:
    from actions.models import Plan


def export_dashboard_report_for_plan(plan: Plan, format: Literal['csv', 'xlsx']):
    report_type = ReportType.generate_for_plan_dashboard(plan)
    report = report_type.generate_incomplete_report()
    report.disable_title_sheet = True
    report.disable_summary_sheets = True
    report.disable_macros = True
    exporter = report.get_xlsx_exporter()
    if format == 'xlsx':
        output = exporter.generate_xlsx()
        filename = exporter.get_filename()
    else:
        output = exporter.generate_csv()
        filename = exporter.get_filename('.csv')
    return output, filename
