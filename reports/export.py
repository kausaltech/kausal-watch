from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from .models import ReportType

if TYPE_CHECKING:
    from actions.models import Plan
    from kausal_common.users import UserOrAnon


def export_dashboard_report_for_plan(plan: Plan, format: Literal['csv', 'xlsx'], user: UserOrAnon):
    report_type = ReportType.generate_for_plan_dashboard(plan, user)
    report = report_type.generate_incomplete_report()
    report.disable_title_sheet = True
    report.disable_summary_sheets = True
    report.disable_macros = True
    exporter = report.get_xlsx_exporter()
    output: str | bytes
    if format == 'xlsx':
        output = exporter.generate_xlsx()
        filename = exporter.get_filename()
    else:
        output = exporter.generate_csv()
        filename = exporter.get_filename('.csv')
    return output, filename
