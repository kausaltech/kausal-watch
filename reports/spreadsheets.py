from datetime import datetime
import inspect

from django.contrib.contenttypes.models import ContentType
from django.utils import translation
from django.utils.translation import gettext as _

from actions.models import Action, Category, ActionImplementationPhase, ActionStatus
from actions.models.category import CategoryType
from orgs.models import Organization

from io import BytesIO

import polars
import xlsxwriter
from xlsxwriter.format import Format

import typing
if typing.TYPE_CHECKING:
    from .models import Report
    from reports.blocks.action_content import ReportFieldBlock

from .utils import make_attribute_path, group_by_model, prepare_serialized_model_version


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
            f.set_num_format('d mmmm yyyy')
            f.set_align('left')
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def odd_row(cls, f: Format):
            f.set_bg_color(cls.BG_COLOR_ODD)

        @classmethod
        def even_row(cls, f: Format):
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def title(cls, f: Format):
            f.set_bold()
            f.set_font_size(24)
            cls.header_row(f)

        @classmethod
        def sub_title(cls, f: Format):
            f.set_bold()
            f.set_font_size(18)
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def metadata_label(cls, f: Format):
            f.set_bold()
            f.set_align('right')
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def metadata_value(cls, f: Format):
            f.set_align('left')
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def sub_sub_title(cls, f: Format):
            f.set_font_size(16)
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def all_rows(cls, f: Format):
            f.set_border(0)
            f.set_align('top')
            f.set_text_wrap(True)

    def __getattr__(self, name):
        return self[name]

    def set_for_field(self, field: 'ReportFieldBlock', labels: list) -> None:
        cell_format = self._formats_for_fields.get(field.id)  # TODO: field.id not key
        if not cell_format:
            cell_format_specs: dict = field.block.get_xlsx_cell_format(field.value)
            cell_format = self.workbook.add_format(cell_format_specs)
            self.StyleSpecifications.all_rows(cell_format)
            for label in labels:
                self._formats_for_fields[label] = cell_format

    def set_for_label(self, label: str, format: Format) -> None:
        cell_format = self._formats_for_fields.get(label)
        if not cell_format:
            self._formats_for_fields[label] = format

    def get_for_label(self, label):
        return self._formats_for_fields.get(label)


class CursorWriter:
    def __init__(self, worksheet, formats=None, default_format=None, start=(0, 0), width=None):
        self.default_format = default_format
        self.worksheet = worksheet
        self.cursor = start
        self.start = start
        self.fill_to = start[1] + width
        self.current_format = None
        self.formats = formats

    def write(self, value, format=None, url=None):
        format = format if format else self.default_format
        self.current_format = format
        x, y = self.cursor
        if url:
            self.worksheet.write_url(x, y, url, format, string=value)
        else:
            self.worksheet.write(x, y, value, format)
        self.cursor = (x, y + 1)
        return self

    def write_empty(self, count):
        while count > 0:
            self.write('', format=self.current_format)
            count -= 1
        return self

    def newline(self):
        x, y = self.cursor
        y_delta = self.fill_to - y
        if y_delta > 0:
            self.write_empty(y_delta)
        self.cursor = (x + 1, self.start[1])
        return self

    def write_cells(self, cells: list[list[tuple[str, str]|tuple[str, str, str]]]):
        for row in cells:
            for cell in row:
                format = cell[1] if len(cell) > 1 else None
                if isinstance(format, str):
                    format = getattr(self.formats, format, None)
                url = None
                if len(cell) > 2:
                    url = cell[2]
                self.write(cell[0], format=format, url=url)
            self.newline()


class ExcelReport:
    language: str
    report: 'Report'
    workbook: xlsxwriter.Workbook
    formats: ExcelFormats
    plan_current_related_objects: 'PlanRelatedObjects'

    class PlanRelatedObjects:
        implementation_phases: dict[int, ActionImplementationPhase]
        organizations: dict[int, Organization]
        categories: dict[int, Category]
        category_types: dict[int, CategoryType]
        statuses: dict[int, ActionStatus]
        action_content_type: ContentType

        def __init__(self, report: 'Report'):
            plan = report.type.plan
            self.category_types = self._keyed_dict(report.type.plan.category_types.all())
            self.categories = self._keyed_dict([c for ct in self.category_types.values() for c in ct.categories.all()])
            self.implementation_phases = self._keyed_dict(plan.action_implementation_phases.all())
            self.statuses = self._keyed_dict(plan.action_statuses.all())
            self.organizations = self._keyed_dict(Organization.objects.available_for_plan(plan))
            self.action_content_type = ContentType.objects.get_for_model(Action)

        @staticmethod
        def _keyed_dict(seq, key='pk'):
            return {getattr(el, key): el for el in seq}

    def __init__(self, report: 'Report', language: str|None = None):
        # Currently only language None is properly supported, defaulting
        # to the plan's primary language. When implementing support for
        # other languages, make sure the action contents and other
        # plan object contents are translated.
        self.language = report.type.plan.primary_language if language is None else language
        self.report = report
        self.output = BytesIO()
        self.workbook = xlsxwriter.Workbook(self.output, {'in_memory': True})
        self.formats = ExcelFormats(self.workbook)
        self.plan_current_related_objects = self.PlanRelatedObjects(self.report)
        self._initialize_formats()

    def generate_actions_dataframe(self) -> polars.DataFrame:
        with translation.override(self.language):
            prepared_data = self._prepare_serialized_report_data()
            return self.create_populated_actions_dataframe(prepared_data)

    def generate_xlsx(self) -> bytes:
        actions_df = self.generate_actions_dataframe()
        with translation.override(self.language):
            self._write_title_sheet()
            self._write_actions_sheet(actions_df)
            self.post_process(actions_df)
        # Make striped even-odd rows
        self.close()
        return self.output.getvalue()

    def _write_title_sheet(self):
        worksheet = self.workbook.add_worksheet(_('Lead'))
        plan = self.report.type.plan
        start = self.report.start_date
        end = self.report.end_date
        complete_key = _('status')
        complete_label = _('complete')
        not_complete_label = _('in progress')
        completed = complete_label if self.report.is_complete else not_complete_label
        cells = [
            [(plan.name, 'title')],
            [(self.report.type.name, 'sub_title')],
            [(self.report.name, 'sub_sub_title')],
            [],
            [(complete_key, 'metadata_label'), (completed, 'metadata_value')],
            [(str(self.report._meta.get_field('start_date').verbose_name), 'metadata_label'), (start, 'date')],
            [(str(self.report._meta.get_field('end_date').verbose_name), 'metadata_label'), (end, 'date')],
            [(_('updated at'), 'metadata_label'), (plan.to_local_timezone(datetime.now()).replace(tzinfo=None), 'date')],
            [],
            [(_('Exported from Kausal Watch'), 'metadata_value')],
            [('kausal.tech', 'metadata_value', 'https://kausal.tech')],
            [],
        ]
        CursorWriter(
            worksheet,
            formats=self.formats,
            default_format=self.formats.even_row,
            width=3
        ).write_cells(cells)
        worksheet.set_row(0, 30)
        worksheet.set_row(1, 30)
        worksheet.set_row(2, 30)
        worksheet.autofit()
        worksheet.set_column(1, 1, 40)

    def _write_actions_sheet(self, df: polars.DataFrame):
        return self._write_sheet(self.workbook.add_worksheet(_('Actions')), df)

    def _write_sheet(self, worksheet: xlsxwriter.worksheet.Worksheet, df: polars.DataFrame, small: bool = False):
        # Header row
        worksheet.write_row(0, 0, df.columns, self.formats.header_row)

        # col_width = 40 if small else 50
        # first_col_width = col_width if small else 10
        # row_height = 20 if small else 50
        # last_col_width = 10 if small else col_width

        col_width = 5
        first_col_width = 5
        row_height = 20 if small else 50
        last_col_width = 5

        # Data rows
        for i, row in enumerate(df.iter_rows()):
            worksheet.write_row(i + 1, 0, row, self.formats.all_rows)
            worksheet.set_row(i + 1, row_height)
        i = 0
        for label in df.columns:
            worksheet.set_column(i, i, col_width, self.formats.get_for_label(label))
            i += 1
        worksheet.set_column(0, 0, first_col_width)
        worksheet.set_column(i-1, i-1, last_col_width)
        worksheet.set_row(0, 20)
        worksheet.autofit()
        if not small:
            worksheet.set_column(1, 1, 50)
        worksheet.conditional_format(1, 0, df.height, df.width-1, {
            'type': 'formula',
            'criteria': '=MOD(ROW(),2)=0',
            'format': self.formats.odd_row
        })
        worksheet.conditional_format(1, 0, df.height, df.width-1, {
            'type': 'formula',
            'criteria': '=NOT(MOD(ROW(),2)=0)',
            'format': self.formats.even_row
        })
        return worksheet

    def close(self):
        self.workbook.close()


    def _prepare_serialized_report_data(self):
        row_data = []
        if self.report.is_complete:
            for snapshot in (
                    self.report.action_snapshots.all()
                    .select_related('action_version__revision__user')
                    .prefetch_related('action_version__revision__version_set')
            ):
                row_data.append(snapshot.get_related_serialized_data())
            return row_data

        # Live incomplete report, although some actions might be completed for report
        for action, all_related_versions, completion in self.report.get_live_action_versions():
            row_data.append(dict(
                action=prepare_serialized_model_version(action),
                related_objects=group_by_model([prepare_serialized_model_version(o) for o in all_related_versions]),
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

        COMPLETED_BY_LABEL = _('Marked as complete by')
        COMPLETED_AT_LABEL = _('Marked as complete at')

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
            append_to_key(_('Identifier'), action_identifier)
            append_to_key(_('Action'), action_name)
            for field in self.report.fields:
                labels = [label for label in field.block.xlsx_column_labels(field.value)]
                values = field.block.extract_action_values(
                    self, field.value, action['data'],
                    action_row['related_objects'],
                )
                assert len(labels) == len(values)
                self.formats.set_for_field(field, labels)
                for label, value in zip(labels, values):
                    append_to_key(label, value)
            append_to_key(COMPLETED_BY_LABEL, completed_by)
            append_to_key(COMPLETED_AT_LABEL, completed_at)
            self.formats.set_for_label(COMPLETED_AT_LABEL, self.formats.date)
        if set(data[COMPLETED_AT_LABEL]) == {None}:
            del data[COMPLETED_AT_LABEL]
            del data[COMPLETED_BY_LABEL]
        return polars.DataFrame(data)

    def _get_aggregates(self, labels: tuple[str], action_df: polars.DataFrame):
        for label in labels:
            if label not in action_df.columns:
                return None
        if len(labels) == 0 or len(labels) > 2:
            raise ValueError('Only one or two dimensional pivot tables supported')
        action_df = action_df.fill_null('[' + _('Unknown') + ']')
        if len(labels) == 1:
            return action_df\
                .groupby(labels)\
                .count()\
                .sort(reversed(labels), descending=False)\
                .rename({'count': _('Actions')})
        return action_df.pivot(
            values=_("Identifier"),
            index=labels[0],
            columns=labels[1],
            aggregate_function="count"
            ).sort(labels[0])

    def post_process(self, action_df: polars.DataFrame):
        pivot_specs = [
            {
                'group': (_('implementation phase').capitalize(),),
                'type': 'pie'
            },
            {
                'group': (
                    _('Parent'),
                    _('implementation phase').capitalize()),
                'type': 'column'
            }
        ]
        for ct in self.plan_current_related_objects.category_types.values():
            pivot_specs.append({
                'group': (ct.name, _('implementation phase').capitalize()),
                'type': 'column',
                'subtype': 'stacked'
            })
        sheet_number = 1
        for spec in pivot_specs:
            grouping = spec['group']
            aggregated = self._get_aggregates(grouping, action_df)
            if aggregated is None:
                continue
            sheet_name = f"Summary {sheet_number}"
            sheet_number += 1
            worksheet = self.workbook.add_worksheet(sheet_name)
            self._write_sheet(worksheet, aggregated, small=True)
            chart_type = spec['type']
            chart = self.workbook.add_chart({'type': chart_type, 'subtype': spec.get('subtype')})
            for i in range(0, aggregated.width - 1):
                series = {
                    'categories': [sheet_name, 1, 0, aggregated.height, 0],
                    'values': [sheet_name, 1, 1 + i, aggregated.height, 1 + i],
                    'name': [sheet_name, 0, 1 + i]
                }
                chart.add_series(series)
            if chart_type == 'column':
                chart.set_size({'width': 720, 'height': 576})
            chart.set_plotarea({
                'gradient': {'colors': ['#FFEFD1', '#F0EBD5', '#B69F66']}
            })
            worksheet.insert_chart('A' + str(aggregated.height + 2), chart)

    def _initialize_format(self, key, initializer):
        format = self.workbook.add_format()
        self.formats[key] = format
        initializer(format)

    def _initialize_formats(self):
        for name, callback in inspect.getmembers(ExcelFormats.StyleSpecifications, inspect.ismethod):
            self._initialize_format(name, callback)
