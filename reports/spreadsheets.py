from django.core.exceptions import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _

from actions.models import Action
from io import BytesIO

import xlsxwriter
from xlsxwriter.worksheet import Worksheet
from xlsxwriter.format import Format

import typing
from typing import Callable
if typing.TYPE_CHECKING:
    from .models import Report, ActionSnapshot


class ExcelFormats:
    @staticmethod
    def header_row(f: Format):
        f.set_font_color('#ffffff')
        f.set_bg_color('#0a5e43')
        f.set_bold()


class ExcelReport:
    # pass as context to block fields
    report: 'Report'
    workbook: xlsxwriter.Workbook
    formats: dict

    def __init__(self, report: 'Report'):
        self.report = report
        self.output = BytesIO()
        self.workbook = xlsxwriter.Workbook(self.output, {'in_memory': True})
        self.formats = dict()

        self._initialize_formats()

    def generate_xlsx(self) -> bytes:
        workbook = self.workbook
        worksheet = workbook.add_worksheet()
        self._write_xlsx_header(worksheet)
        self._write_xlsx_action_rows(workbook, worksheet)
        worksheet.autofit()
        # Set width of some columns explicitly
        worksheet.set_column(0, 0, 60)  # Action
        worksheet.set_column(1, 1, 40)  # Marked as complete by #to end
        worksheet.set_column(2, 2, 40)  # Marked as complete by
        self.post_process()
        self.close()
        return self.output.getvalue()

    def close(self):
        self.workbook.close()

    def _write_xlsx_header(self, worksheet: Worksheet):
        worksheet.set_row(0, 20, self.formats['header_row'])
        worksheet.write(0, 0, str(_('Action')))
        worksheet.write(0, 1, str(_('Marked as complete by')))
        worksheet.write(0, 2, str(_('Marked as complete at')))
        column = 3
        for field in self.report.fields:
            for label in field.block.xlsx_column_labels(field.value):
                worksheet.write(0, column, label)
                column += 1

    def _write_xlsx_action_rows(self, workbook: xlsxwriter.Workbook, worksheet: xlsxwriter.Workbook.worksheet_class):
        self._xlsx_cell_format_for_field = {}
        self._xlsx_cell_format_for_date = workbook.add_format({'num_format': 'yyyy-mm-dd h:mm:ss'})
        self._xlsx_cell_format_for_odd_rows = workbook.add_format({'bg_color': '#f4f4f4'})
        self._xlsx_cell_format_for_name_odd = workbook.add_format({'text_wrap': True, 'bg_color': '#f4f4f4'})
        self._xlsx_cell_format_for_name_even = workbook.add_format({'text_wrap': True})
        row = 1
        # For complete reports, we only want to write actions for which we have a snapshot. For incomplete reports, we
        # also want to include the current state of actions for which there is no snapshot.
        if self.report.is_complete:
            for snapshot in self.report.action_snapshots.all():
                self._write_xlsx_action_row(workbook, worksheet, snapshot, row)
                row += 1
        else:
            for action in self.report.type.plan.actions.all():
                try:
                    snapshot = action.get_latest_snapshot(self.report)
                except ObjectDoesNotExist:
                    self._write_xlsx_action_row(workbook, worksheet, action, row)
                else:
                    self._write_xlsx_action_row(workbook, worksheet, snapshot, row)
                row += 1

    def _write_xlsx_action_row(
        self, workbook: xlsxwriter.Workbook, worksheet: xlsxwriter.Workbook.worksheet_class, action_or_snapshot, row,
    ):
        from .models import ActionSnapshot  # FIXME
        # FIXME: action_or_snapshot can be an Action or ActionSnapshot, but distinguishing the cases is ugly. Improve.
        if isinstance(action_or_snapshot, ActionSnapshot):
            # Instead of fucking around with the `name` and `i18n` fields to simulate `name_i18n`, just build a fake
            # model instance
            field_dict = action_or_snapshot.action_version.field_dict
            action_name = str(Action(**{key: field_dict[key] for key in ['identifier', 'name', 'plan_id', 'i18n']}))
            # Get creation date and user from the version's revision
            revision = action_or_snapshot.action_version.revision
            # Excel can't handle timezones
            completed_at = self.report.type.plan.to_local_timezone(revision.date_created).replace(tzinfo=None)
            completed_by = revision.user
            # FIXME: Right now, we print the user who made the last change to the action, which may be different from
            # the user who marked the action as complete.
        else:
            assert isinstance(action_or_snapshot, Action)
            action_name = str(action_or_snapshot)
            completed_at = None
            completed_by = None
        style = workbook.add_format() if row % 2 else self._xlsx_cell_format_for_odd_rows
        name_style = self._xlsx_cell_format_for_name_even if row % 2 else self._xlsx_cell_format_for_name_odd
        name_style.set_align('top')
        worksheet.set_row(row, 40, style)
        worksheet.write(row, 0, action_name, name_style)
        if completed_by:
            worksheet.write(row, 1, str(completed_by))
        if completed_at:
            style = self._xlsx_cell_format_for_date
            worksheet.write(row, 2, completed_at, style)
        column = 3
        for field in self.report.fields:
            if isinstance(action_or_snapshot, ActionSnapshot):
                values = field.block.xlsx_values_for_action_snapshot(field.value, action_or_snapshot)
            else:
                values = field.block.xlsx_values_for_action(field.value, action_or_snapshot)
            for value in values:
                # Add cell format only once per field and cache added formats
                cell_format = self._xlsx_cell_format_for_field.get(field.id)
                if not cell_format:
                    cell_format = field.block.add_xlsx_cell_format(field.value, workbook)
                    self._xlsx_cell_format_for_field[field.id] = cell_format
                worksheet.write(row, column, value, cell_format)
                column += 1

    def post_process(self):
        pass
        # pivot_worksheet = self.workbook.add_worksheet()
        # return self.workbook

    def _initialize_format(self, key, initializer):
        format = self.workbook.add_format()
        self.formats[key] = format
        initializer(format)

    def _initialize_formats(self):
        for name, callback in ExcelFormats.__dict__.items():
            if not isinstance(callback, Callable):
                continue
            self._initialize_format(name, callback)
