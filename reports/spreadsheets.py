import inspect

from django.utils import translation
from django.utils.translation import gettext as _

from actions.models import Action, Category, ActionImplementationPhase, ActionStatus
from actions.models.category import CategoryType
from orgs.models import Organization
from reports.blocks.action_content import ActionCategoryReportFieldBlock

from io import BytesIO

import polars
import xlsxwriter
from xlsxwriter.format import Format

import typing
if typing.TYPE_CHECKING:
    from .models import Report
    from reports.blocks.action_content import ReportFieldBlock


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
        def even_row(cls, f: Format):
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def all_rows(cls, f: Format):
            f.set_border(0)
            f.set_align('top')
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

        def __init__(self, report: 'Report'):
            plan = report.type.plan
            self.implementation_phases = {
                p.pk: p for p in plan.action_implementation_phases.all()
            }
            self.statuses = {
                p.pk: p for p in plan.action_statuses.all()
            }
            self.organizations = {
                p.pk: p for p in Organization.objects.available_for_plan(plan)
            }
            category_types = [
                field.value.get('category_type')
                for field in report.fields
                if isinstance(field.block, ActionCategoryReportFieldBlock)
            ]
            self.category_types = {
                ct.pk: ct for ct in category_types
            }
            self.categories = {
                c.pk: c for ct in category_types for c in ct.categories.all()
            }

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
            self._write_actions_sheet(actions_df)
            self.post_process(actions_df)
        # Make striped even-odd rows
        self.close()
        return self.output.getvalue()

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
            if completed_by:
                append_to_key(_('Marked as complete by'), completed_by)
            if completed_at:
                append_to_key(_('Marked as complete at'), completed_at)
        return polars.DataFrame(data)

    def _get_aggregates(self, labels: tuple[str], action_df: polars.DataFrame):
        for label in labels:
            if label not in action_df.columns:
                return None
        if len(labels) == 0 or len(labels) > 2:
            raise ValueError('Only one or two dimensional pivot tables supported')
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
                'group': (_('parent organization').capitalize(),
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
