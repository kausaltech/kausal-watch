"""The reports of an action's reporting tab: its values in the latest reports of each template, and submitting to them."""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from itertools import groupby
from typing import TYPE_CHECKING, Any

from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format, number_format
from django.utils.http import urlencode
from django.utils.translation import gettext as _, pgettext
from wagtail.admin.panels import Panel

from loguru import logger

from .models import ActionListPageNotFoundError, ActionSnapshot, Report
from .submissions import user_can_submit_action
from .types import SerializedActionVersion, SerializedVersion

if TYPE_CHECKING:
    from kausal_common.users import UserOrAnon

    from actions.models import Action

    from .models import ReportType
    from .spreadsheets.excel_report import ExcelReport

# How many of each template's reports the tab compares, latest first
REPORTS_PER_TEMPLATE = 3


@dataclass(frozen=True)
class ReportColumn:
    """An action's values in one report, and what its editor can do about its submission there."""

    report: Report
    snapshot: ActionSnapshot | None
    values: list[str]
    submit_url: str | None = None
    resubmit_url: str | None = None

    @property
    def submitted_at(self) -> datetime.datetime | None:
        """Return when the action was submitted to the report by an editor, not captured by completing the report."""
        if self.snapshot is None or not self.snapshot.created_explicitly:
            return None
        return self.snapshot.action_version.revision.date_created

    @property
    def is_captured(self) -> bool:
        """Return whether the report keeps the action's data from a snapshot, rather than its current data."""
        return self.snapshot is not None


@dataclass(frozen=True)
class ReportTable:
    """An action's values in the latest reports of a template, one column per report."""

    report_type: ReportType
    labels: list[str]
    columns: list[ReportColumn]

    @property
    def rows(self) -> list[tuple[str, list[str]]]:
        return [(label, [column.values[index] for column in self.columns]) for index, label in enumerate(self.labels)]


def _display(value: Any) -> str:
    if value is None or value == '':
        return '—'
    if isinstance(value, datetime.datetime):
        return date_format(timezone.localtime(value) if timezone.is_aware(value) else value, 'DATE_FORMAT')
    if isinstance(value, datetime.date):
        return date_format(value, 'DATE_FORMAT')
    if isinstance(value, float):
        return number_format(value)
    return str(value)


def _reserved_labels() -> set[str]:
    """Return the column labels of the spreadsheet export that are not the template's fields."""
    # As `ExcelReport.create_populated_actions_dataframe` names them
    return {
        _('Identifier'),
        pgettext('Action model', 'Action'),
        _('Plan'),
        _('Marked as complete by'),
        _('Marked as complete at'),
    }


def _versions(
    action: Action, report: Report, snapshot: ActionSnapshot | None, user: UserOrAnon
) -> tuple[list[SerializedActionVersion], list[SerializedVersion]]:
    """Return the action's data in the report: its snapshot, or else its current data while the report is open."""
    if snapshot is not None:
        related = [SerializedVersion.from_version_polymorphic(version) for version in snapshot.get_related_versions()]
        return [snapshot.get_serialized_data()], related
    if report.is_complete:
        # The action did not exist yet, or was not visible, when the report was completed
        return [], []
    live = report.get_live_versions(action_ids=[action.pk], user=user)
    actions = [SerializedActionVersion.from_version(version) for version in live.actions]
    related = [SerializedVersion.from_version_polymorphic(version) for version in live.related]
    return actions, related


def _row(
    exporter: ExcelReport, action: Action, report: Report, snapshot: ActionSnapshot | None, user: UserOrAnon
) -> dict[str, Any] | None:
    actions, related = _versions(action, report, snapshot, user)
    if not actions:
        return None
    dataframe = exporter.create_populated_actions_dataframe(actions, related)
    return dataframe.row(0, named=True) if dataframe.height else None


def _submission_urls(action: Action, report: Report, snapshot: ActionSnapshot | None, user) -> dict[str, str]:
    if report.is_complete or not user_can_submit_action(user, action, report):
        return {}
    return_url = f'{reverse("actions_action_modeladmin_edit", args=(action.pk,))}#tab-reporting'
    query = urlencode({'next': return_url})
    kwargs = {'action_pk': action.pk, 'report_pk': report.pk}
    if snapshot is None:
        return {'submit_url': f'{reverse("actions_action_modeladmin_mark_action_as_complete", kwargs=kwargs)}?{query}'}
    return {'resubmit_url': f'{reverse("actions_action_modeladmin_resubmit_action_for_report", kwargs=kwargs)}?{query}'}


def get_action_report_tables(action: Action, user) -> list[ReportTable]:
    """
    Return the action's values in the latest reports of each template shown in the reporting tab.

    The values are those of the action's submission, or of its current data while it has not been submitted to an open
    report, formatted as the report's spreadsheet export formats them.
    """
    reports = (
        Report.objects
        .filter(type__plan=action.plan, show_in_reporting_tab=True)
        .select_related('type__plan')
        .order_by('type__name', 'type_id', '-start_date')
    )
    tables: list[ReportTable] = []
    for report_type, type_reports in groupby(reports, key=lambda report: report.type):
        latest_reports = list(type_reports)[:REPORTS_PER_TEMPLATE]
        try:
            exporter = latest_reports[0].get_xlsx_exporter(action_ids=[action.pk], user=user)
        except ActionListPageNotFoundError:
            logger.warning(f'Cannot show report template {report_type} in the reporting tab: the plan has no action list')
            continue
        rows = []
        for report in latest_reports:
            try:
                snapshot = action.get_latest_snapshot(report)
            except ActionSnapshot.DoesNotExist:
                snapshot = None
            rows.append((report, snapshot, _row(exporter, action, report, snapshot, user)))
        reserved = _reserved_labels()
        labels: list[str] = []
        for _report, _snapshot, row in rows:
            for label in row or {}:
                if label not in reserved and label not in labels:
                    labels.append(label)
        columns = [
            ReportColumn(
                report=report,
                snapshot=snapshot,
                values=[_display((row or {}).get(label)) for label in labels],
                **_submission_urls(action, report, snapshot, user),
            )
            for report, snapshot, row in rows
        ]
        tables.append(ReportTable(report_type=report_type, labels=labels, columns=columns))
    return tables


class ActionReportsPanel(Panel):
    """Compare an action's values in the latest reports of each template, and submit it to the open ones."""

    class BoundPanel(Panel.BoundPanel):
        template_name = 'reports/panels/action_reports_panel.html'

        def is_shown(self):
            return self.instance is not None and self.instance.pk is not None

        def get_context_data(self, parent_context=None):
            from actions.models import Action

            context = super().get_context_data(parent_context)
            action = self.instance
            assert isinstance(action, Action)
            context['tables'] = get_action_report_tables(action, self.request.user)
            return context
