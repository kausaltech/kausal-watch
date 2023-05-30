import inspect

from django.utils.translation import gettext_lazy as _

from actions.models import Action
from io import BytesIO

import xlsxwriter
from xlsxwriter.worksheet import Worksheet
from xlsxwriter.format import Format

import typing
if typing.TYPE_CHECKING:
    from .models import Report


class ExcelFormats(dict):
    workbook: xlsxwriter.Workbook
    _formats_for_fields: dict

    def __init__(self, workbook, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workbook = workbook
        self._formats_for_fields = dict()

    class StyleSpecifications:
        BG_COLOR_ODD = '#f4f4f4'
        BG_COLOR_HEADER = '#0a5e43'
        COLOR_WHITE = '#ffffff'

        @classmethod
        def header_row(cls, f: Format):
            f.set_font_color('#ffffff')
            f.set_bg_color(cls.BG_COLOR_HEADER)
            f.set_bold()

        @classmethod
        def date(cls, f: Format):
            f.set_num_format('yyyy-mm-dd h:mm:ss')

        @classmethod
        def name(cls, f: Format):
            f.set_align('vcenter')
            f.set_text_wrap(True)

        @classmethod
        def odd_row(cls, f: Format):
            f.set_bg_color(cls.BG_COLOR_ODD)

        @classmethod
        def all_rows(cls, f: Format):
            f.set_border(0)
            f.set_align('vcenter')
            f.set_bg_color(cls.COLOR_WHITE)

    def __getattr__(self, name):
        return self[name]

    def for_field(self, field):
        cell_format = self._formats_for_fields.get(field.id)
        if not cell_format:
            cell_format_specs: dict = field.block.get_xlsx_cell_format(field.value)
            cell_format = self.workbook.add_format(cell_format_specs)
            self.StyleSpecifications.all_rows(cell_format)
            self._formats_for_fields[field.id] = cell_format
        return cell_format


class ExcelReport:
    # pass as context to block fields
    report: 'Report'
    workbook: xlsxwriter.Workbook
    formats: ExcelFormats

    def __init__(self, report: 'Report'):
        self.report = report
        self.output = BytesIO()
        self.workbook = xlsxwriter.Workbook(self.output, {'in_memory': True})
        self.formats = ExcelFormats(self.workbook)

        self._initialize_formats()

    def generate_xlsx(self) -> bytes:
        workbook = self.workbook
        worksheet = workbook.add_worksheet()
        self._write_xlsx_header(worksheet)
        self._write_xlsx_action_rows(workbook, worksheet)
        worksheet.autofit()
        # Set width of some columns explicitly
        worksheet.set_column(0, 0, 80)  # Action
        worksheet.conditional_format(1, 0, 1000, 10, {
            'type': 'formula',
            'criteria': '=MOD(ROW(),2)=0',
            'format': self.formats.odd_row
        })
        self.post_process()
        self.close()
        return self.output.getvalue()

    def close(self):
        self.workbook.close()

    def _write_xlsx_header(self, worksheet: Worksheet):
        worksheet.set_row(0, 20, self.formats.header_row)
        worksheet.write(0, 0, str(_('Action')))
        column = 1
        for field in self.report.fields:
            for label in field.block.xlsx_column_labels(field.value):
                worksheet.write(0, column, label)
                column += 1
        worksheet.write(0, column + 1, str(_('Marked as complete by')))
        worksheet.write(0, column + 2, str(_('Marked as complete at')))

    def _prepare_serialized_model_version(self, version):
        return dict(
            type=version.content_type.model_class,
            data=version.field_dict
        )

    def _prepare_serialized_report_data(self):
        row_data = []
        if self.report.is_complete:
            for snapshot in self.report.action_snapshots.all():
                related_objects = snapshot.get_related_versions()
                revision = snapshot.action_version.revision
                row_data.append(dict(
                    action=self._prepare_serialized_model_version(snapshot.action_version),
                    related_objects=[self._prepare_serialized_model_version(o) for o in related_objects],
                    completion={
                        'completed_at': revision.date_created,
                        'completed_by': revision.user
                    }
                ))
            return row_data

        # Live report, not complete, although some actions might be
        for action, related_objects, completion in self.report.get_live_action_versions():
            row_data.append(dict(
                action=self._prepare_serialized_model_version(action),
                related_objects=[self._prepare_serialized_model_version(o) for o in related_objects],
                completion=completion
            ))
        return row_data

    def _write_xlsx_action_rows(self, workbook: xlsxwriter.Workbook, worksheet: xlsxwriter.Workbook.worksheet_class):
        # For complete reports, we only want to write actions for which we have a snapshot. For incomplete reports, we
        # also want to include the current state of actions for which there is no snapshot.
        prepared_data = self._prepare_serialized_report_data()
        for i, data in enumerate(prepared_data):
            self._write_xlsx_action_row(worksheet, data, i + 1)

    def _write_xlsx_action_row(
        self,
        worksheet: xlsxwriter.Workbook.worksheet_class,
        data: dict, row: int
    ):
        action = data['action']
        action_name = str(Action(**{key: action['data'][key] for key in ['identifier', 'name', 'plan_id', 'i18n']})).replace("\n", " ")

        # FIXME: Right now, we print the user who made the last change to the action, which may be different from
        # the user who marked the action as complete.
        completed_by = data['completion']['completed_by']
        completed_at = data['completion']['completed_at']
        if completed_at is not None:
            completed_at = self.report.type.plan.to_local_timezone(completed_at).replace(tzinfo=None)

        worksheet.set_row(row, 50, self.formats.all_rows)
        worksheet.write(row, 0, action_name, self.formats.name)
        column = 1
        for field in self.report.fields:
            values = field.block.extract_action_values(
                self, field.value, action, data['related_objects']
            )
            # if isinstance(action_or_snapshot, ActionSnapshot):
            #     values = field.block.xlsx_values_for_action_snapshot(field.value, action_or_snapshot)
            # else:
            #     values = field.block.xlsx_values_for_action(field.value, action_or_snapshot)
            for value in values:
                # Add cell format only once per field and cache added formats
                cell_format = self.formats.for_field(field)
                worksheet.write(row, column, value, cell_format)
                column += 1
        if completed_by:
            worksheet.write(row, column + 1, str(completed_by))
        if completed_at:
            worksheet.write(row, column + 2, completed_at, self.formats.date)

    def post_process(self):
        pass
        # pivot_worksheet = self.workbook.add_worksheet()
        # return self.workbook

    def _initialize_format(self, key, initializer):
        format = self.workbook.add_format()
        self.formats[key] = format
        initializer(format)

    def _initialize_formats(self):
        for name, callback in inspect.getmembers(ExcelFormats.StyleSpecifications, inspect.ismethod):
            self._initialize_format(name, callback)
