from pprint import pprint as pr
import inspect

from django.utils.translation import gettext

from actions.models import Action, ActionResponsibleParty
from orgs.models import Organization

from io import BytesIO

import polars
import xlsxwriter
from xlsxwriter.format import Format

import typing
if typing.TYPE_CHECKING:
    from .models import Report
    from reports.blocks.action_content import ReportFieldBlock


LABEL_IDENTIFIER = gettext('Identifier')
LABEL_ACTION_NAME = gettext('Action')
LABEL_COMPLETED_BY = gettext('Marked as complete by'),
LABEL_COMPLETED_AT = gettext('Marked as complete at')


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
        def odd_row(cls, f: Format):
            f.set_bg_color(cls.BG_COLOR_ODD)

        @classmethod
        def all_rows(cls, f: Format):
            f.set_border(0)
            f.set_align('top')
            f.set_bg_color(cls.COLOR_WHITE)
            f.set_text_wrap(True)

    def __getattr__(self, name):
        return self[name]

    def set_for_field(self, field: 'ReportFieldBlock', labels: list) -> None:
        cell_format = self._formats_for_fields.get(field.id)
        if not cell_format:
            cell_format_specs: dict = field.block.get_xlsx_cell_format(field.value)
            cell_format = self.workbook.add_format(cell_format_specs)
            self.StyleSpecifications.all_rows(cell_format)
            for label in labels:
                self._formats_for_fields[label] = cell_format

    def get_for_label(self, label):
        return self._formats_for_fields.get(label)


class ExcelReport:
    # pass as context to block fields
    report: 'Report'
    workbook: xlsxwriter.Workbook
    formats: ExcelFormats
    plan_current_related_objects: dict

    def __init__(self, report: 'Report'):
        self.report = report

        self.output = BytesIO()
        self.workbook = xlsxwriter.Workbook(self.output, {'in_memory': True})
        self.formats = ExcelFormats(self.workbook)

        self._initialize_plan_current_related_objects()
        self._initialize_formats()

    def _initialize_plan_current_related_objects(self):
        plan = self.report.type.plan
        result = dict()
        result['implementation_phase'] = {p.pk: p for p in plan.action_implementation_phases.all()}
        result['organization'] = {p.pk: p for p in Organization.objects.available_for_plan(plan)}
        self.plan_current_related_objects = result

    def get_plan_object(self, model_name: str, pk: int):
        return self.plan_current_related_objects.get(model_name, {}).get(pk)

    def generate_xlsx(self) -> bytes:
        prepared_data = self._prepare_serialized_report_data()
        actions_df = self.create_populated_actions_dataframe(prepared_data)
        worksheet = self._write_actions_sheet(actions_df)

        worksheet.conditional_format(1, 0, 1000, 10, {
            'type': 'formula',
            'criteria': '=MOD(ROW(),2)=0',
            'format': self.formats.odd_row
        })
        # self.post_process(prepared_data)
        self.close()
        return self.output.getvalue()

    def _write_actions_sheet(self, df: polars.DataFrame):
        worksheet = self.workbook.add_worksheet(gettext('Actions'))

        # Header row
        worksheet.write_row(0, 0, df.columns)

        # Data rows
        for i, row in enumerate(df.iter_rows()):
            worksheet.write_row(i + 1, 0, row)
            worksheet.set_row(i + 1, 80, self.formats.all_rows)
        for i, label in enumerate(df.columns):
            worksheet.set_column(i, i, 80, self.formats.get_for_label(label))
        worksheet.set_column(0, 0, 10)
        worksheet.set_row(0, 20, self.formats.header_row)
        return worksheet

    def close(self):
        self.workbook.close()

    def _prepare_serialized_model_version(self, version):
        return dict(
            type=version.content_type.model_class(),
            data=version.field_dict,
            str=version.object_repr
        )

    def _prepare_serialized_report_data(self):
        row_data = []
        if self.report.is_complete:
            for snapshot in self.report.action_snapshots.all():
                all_related_versions = snapshot.get_related_versions()
                revision = snapshot.action_version.revision
                row_data.append(dict(
                    action=self._prepare_serialized_model_version(snapshot.action_version),
                    related_objects=[self._prepare_serialized_model_version(o) for o in all_related_versions],
                    completion={
                        'completed_at': revision.date_created,
                        'completed_by': revision.user
                    }
                ))
            return row_data

        # Live incomplete report, although some actions might be completed for report
        for action, all_related_versions, completion in self.report.get_live_action_versions():
            row_data.append(dict(
                action=self._prepare_serialized_model_version(action),
                related_objects=[self._prepare_serialized_model_version(o) for o in all_related_versions],
                completion=completion
            ))
        return row_data

    def create_populated_actions_dataframe(
            self,
            all_actions: list
    ):
        data = {}

        def append_to_key(key, value):
            data.setdefault(key, []).append(value)

        for action_row in all_actions:
            action = action_row['action']
            action_identifier = action['data']['identifier']
            action_obj = Action(**{key: action['data'][key] for key in ['identifier', 'name', 'plan_id', 'i18n']})
            action_name = action_obj.name.replace("\n", " ")

            # FIXME: Right now, we print the user who made the last change to the action, which may be different from
            # the user who marked the action as complete.
            completion = action_row['completion']
            completed_by = completion['completed_by']
            completed_at = completion['completed_at']
            if completed_at is not None:
                completed_at = self.report.type.plan.to_local_timezone(completed_at).replace(tzinfo=None)
            append_to_key(LABEL_IDENTIFIER, action_identifier)
            append_to_key(LABEL_ACTION_NAME, action_name)
            for field in self.report.fields:
                labels = field.block.xlsx_column_labels(field.value)
                values = field.block.extract_action_values(
                    self, field.value, action['data'],
                    action_row['related_objects'],
                )
                assert len(labels) == len(values)
                self.formats.set_for_field(field, labels)
                for label, value in zip(labels, values):
                    append_to_key(label, value)
            if completed_by:
                append_to_key(LABEL_COMPLETED_BY, completed_by)
            if completed_at:
                append_to_key(LABEL_COMPLETED_AT, completed_at)
        return polars.DataFrame(data)

    def _group_by_org_and_phase(self, data):
        # TODO re-implement using proper data abstraction
        counts = dict()
        for row in data:
            action = row['action']['data']
            responsibles = [
                r['str'].split('(')[0] for r in row['related_objects']
                if r['type'] == ActionResponsibleParty and r['data']['action_id'] == action['id'] and
                r['data']['role'] == 'primary'
            ]
            pk = action.get('implementation_phase_id')
            phase = 'unknown'
            r = 'unknown'
            if pk is not None:
                phase = str(self.get_plan_object('implementation_phase', int(pk)))
            if len(responsibles) > 0:
                r = responsibles[0]
            counts.setdefault(r, {})
            counts[r].setdefault(phase, 0)
            counts[r][phase] = counts[r][phase] + 1
        return counts

    def post_process(self, prepared_data):
        sheet_name = gettext('Responsibilities')
        pivot_worksheet = self.workbook.add_worksheet(sheet_name)
        chart = self.workbook.add_chart({'type': 'column'})
        grouped1 = self._group_by_org_and_phase(prepared_data)
        all_phases = set()
        for v in grouped1.values():
            for k in v.keys():
                all_phases.add(k)
        table_data = []
        for org, group in grouped1.items():
            row = [org]
            for phase in all_phases:
                row.append(group.get(phase, 0))
            table_data.append(row)
        table_data = sorted(table_data, key=lambda x: -(x[1] + x[2]))
        pivot_worksheet.add_table(
            1, 1, len(table_data), len(all_phases) + 1, {
                'data': table_data,
                'banded_rows': True,
                'columns': [{'header': gettext('Organization')}] +
                [{'header': phase} for phase in all_phases]
            }
        )
        # pivot_worksheet.autofit()
        for i, phase in enumerate(all_phases):
            chart.add_series(
                {'categories': [sheet_name, 2, 1, len(table_data), 1],
                 'values': [sheet_name, 2, 2 + i, len(table_data), 2 + i],
                 'name': [sheet_name, 1, 2 + i]}
            )
        pivot_worksheet.insert_chart('B' + str(len(table_data) + 2), chart)

    def _initialize_format(self, key, initializer):
        format = self.workbook.add_format()
        self.formats[key] = format
        initializer(format)

    def _initialize_formats(self):
        for name, callback in inspect.getmembers(ExcelFormats.StyleSpecifications, inspect.ismethod):
            self._initialize_format(name, callback)
