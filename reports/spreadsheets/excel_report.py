from __future__ import annotations
import inspect
import polars
import typing
from typing import Sequence
import xlsxwriter
from datetime import datetime
from django.contrib.contenttypes.models import ContentType
from django.db.models import QuerySet
from django.utils import translation
from django.utils import timezone
from django.utils.translation import gettext as _, pgettext
from io import BytesIO
from reversion.models import Version
from xlsxwriter.format import Format

from reports.utils import group_by_model
from actions.models.action import Action, ActionImplementationPhase, ActionStatus
from actions.models.category import Category, CategoryType
from orgs.models import Organization

from .action_print_layout import write_action_summaries
from .cursor_writer import CursorWriter, Cell


if typing.TYPE_CHECKING:
    from reports.models import ActionSnapshot, Report, SerializedActionVersion, SerializedVersion
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
        COLOR_LIGHT_HEADER = '#f0f0f0'
        COLOR_PAGE_HEADER = '#3c504a'

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
        def timestamp(cls, f: Format):
            cls.date(f)
            f.set_num_format('d mmmm yyyy hh:mm')

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

        @classmethod
        def action_digest_value(cls, f: Format):
            f.set_font_size(8)
            f.set_left()
            f.set_bottom()
            f.set_right()
            f.set_align('vjustify')
            f.set_text_wrap(True)

        @classmethod
        def action_digest_label(cls, f: Format):
            f.set_bg_color(cls.COLOR_LIGHT_HEADER)
            f.set_font_size(8)
            f.set_left()
            f.set_top()
            f.set_right()
            f.set_align('vjustify')
            f.set_text_wrap(True)

        @classmethod
        def action_digest_page_header(cls, f: Format):
            f.set_bg_color(cls.COLOR_PAGE_HEADER)
            f.set_color('#ffffff')
            f.set_align('top')
            f.set_font_size(10)
            f.set_bold()
            f.set_align('vjustify')
            f.set_text_wrap(True)

        @classmethod
        def action_digest_value_long(cls, f: Format):
            cls.action_digest_value(f)
            f.set_bold(False)
            f.set_font_size(8)
            f.set_align('top')
            f.set_align('vjustify')
            f.set_text_wrap(True)

    def __getattr__(self, name):
        return self[name]

    def set_for_field(self, field: 'ReportFieldBlock', labels: list) -> None:
        if None not in set((self._formats_for_fields.get(label) for label in labels)):
            return
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


class ExcelReport:
    language: str
    report: 'Report'
    workbook: xlsxwriter.Workbook
    formats: ExcelFormats
    plan_current_related_objects: 'PlanRelatedObjects'
    field_to_column_labels: dict[str, set[str]]

    class PlanRelatedObjects:
        implementation_phases: dict[int, ActionImplementationPhase]
        organizations: dict[int, Organization]
        categories: dict[int, Category]
        category_types: dict[int, CategoryType]
        statuses: dict[int, ActionStatus]
        action_content_type: ContentType

        def __init__(self, report: 'Report'):
            plan = report.type.plan
            self.category_types = self._keyed_dict(plan.category_types.all())
            self.categories = self._keyed_dict([c for ct in self.category_types.values() for c in ct.categories.all()])
            self.implementation_phases = self._keyed_dict(plan.action_implementation_phases.all())
            self.statuses = self._keyed_dict(plan.action_statuses.all())
            self.organizations = self._keyed_dict(Organization.objects.available_for_plan(plan))
            self.action_content_type = ContentType.objects.get_for_model(Action)
            self.category_level_category_mappings = {
                ct.pk: ct.categories_projected_by_level() for ct in self.category_types.values()
            }

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
        self.field_to_column_labels = dict()
        self._initialize_formats()

    def generate_actions_dataframe(self) -> polars.DataFrame:
        with translation.override(self.language):
            action_version_data, related_versions = self._prepare_serialized_report_data()
            return self.create_populated_actions_dataframe(action_version_data, related_versions)

    def generate_xlsx(self) -> bytes:
        actions_df = self.generate_actions_dataframe()
        with translation.override(self.language):
            self._write_title_sheet()
            self._write_actions_sheet(actions_df)
            self.post_process(actions_df)
        # Make striped even-odd rows
        self.close()
        return self.output.getvalue()

    def _write_title_sheet(self) -> None:
        worksheet = self.workbook.add_worksheet(_('Lead'))
        plan = self.report.type.plan
        start = self.report.start_date
        end = self.report.end_date
        complete_key = _('status')
        complete_label = _('complete')
        not_complete_label = _('in progress')
        completed = complete_label if self.report.is_complete else not_complete_label
        cells: Sequence[Sequence[Cell]] = [
            [Cell(plan.name, 'title')],
            [Cell(self.report.type.name, 'sub_title')],
            [Cell(self.report.name, 'sub_sub_title')],
            [],
            [Cell(complete_key, 'metadata_label'), Cell(completed, 'metadata_value')],
            [Cell(str(self.report._meta.get_field('start_date').verbose_name), 'metadata_label'), Cell(start, 'date')],
            [Cell(str(self.report._meta.get_field('end_date').verbose_name), 'metadata_label'), Cell(end, 'date')],
            [Cell(_('updated at'), 'metadata_label'), Cell(plan.to_local_timezone(datetime.now()).replace(tzinfo=None), 'date')],
            [],
            [Cell(_('Exported from Kausal Watch'), 'metadata_value')],
            [Cell('kausal.tech', 'metadata_value', url='https://kausal.tech')],
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

        # col_width = 40 if small else 50
        # first_col_width = col_width if small else 10
        # row_height = 20 if small else 50
        # last_col_width = 10 if small else col_width

        col_width = 50
        first_col_width = 5
        row_height = 20 if small else 50
        last_col_width = 30

        # Data rows
        for i, row in enumerate(df.iter_rows()):
            worksheet.write_row(i + 1, 0, row)
            worksheet.set_row(i + 1, row_height)
        i = 0
        for label in df.columns:
            format = self.formats.get_for_label(label)
            if format is None:
                format = self.formats.all_rows
            width: int | None = col_width
            if i == 0:
                width = first_col_width
            elif i == len(df.columns) - 1:
                width = last_col_width
            if small:
                width = None
            worksheet.set_column(i, i, width, format)
            i += 1
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
        # Header row
        worksheet.set_row(0, 20)
        worksheet.write_row(0, 0, df.columns, self.formats.header_row)
        if small:
            worksheet.autofit()
        return worksheet

    def close(self):
        self.workbook.close()

    def _prepare_serialized_report_data(self) -> tuple[list[SerializedActionVersion], list[SerializedVersion]]:
        from reports.models import SerializedActionVersion, SerializedVersion
        if self.report.is_complete:
            serialized_actions: list[SerializedActionVersion] = []
            snapshots = (
                self.report.action_snapshots.all()
                .select_related('action_version__revision__user')
                .prefetch_related('action_version__revision__version_set')
            )
            snapshots = typing.cast(typing.Iterable['ActionSnapshot'], snapshots)
            related_versions: QuerySet[Version] = Version.objects.none()
            for snapshot in snapshots:
                action_version_data = snapshot.get_serialized_data()
                serialized_actions.append(action_version_data)
                related_versions |= snapshot.get_related_versions()
            serialized_related = [SerializedVersion.from_version_polymorphic(v) for v in related_versions]
            return serialized_actions, serialized_related

        # Live incomplete report, although some actions might be completed for report
        live_versions = self.report.get_live_versions()
        serialized_actions = [SerializedActionVersion.from_version(v) for v in live_versions.actions]
        serialized_related = [SerializedVersion.from_version_polymorphic(v) for v in live_versions.related]
        return serialized_actions, serialized_related

    def get_column_labels(self, field_name: str) -> set[str]:
        return self.field_to_column_labels.get(field_name, set())

    def create_populated_actions_dataframe(
            self,
            all_actions: list[SerializedActionVersion],
            all_related_versions: list[SerializedVersion],
    ):
        from reports.models import SerializedAttributeVersion
        data = {}

        def append_to_key(key, value, field_name):
            self.field_to_column_labels.setdefault(field_name, set()).add(key)
            data.setdefault(key, []).append(value)

        COMPLETED_BY_LABEL = _('Marked as complete by')
        COMPLETED_AT_LABEL = _('Marked as complete at')

        related_objects = group_by_model(all_related_versions)
        attribute_versions = {
            v.attribute_path: v
            for v in all_related_versions
            if isinstance(v, SerializedAttributeVersion)
        }
        for action in all_actions:
            action_identifier = action.data['identifier']
            action_obj = Action(**{key: action.data[key] for key in ['identifier', 'name', 'plan_id', 'i18n']})
            action_name = action_obj.name.replace("\n", " ")

            # FIXME: Right now, we print the user who made the last change to the action, which may be different from
            # the user who marked the action as complete.
            completed_by = action.completed_by
            completed_at = action.completed_at
            if completed_at is not None:
                completed_at = timezone.make_naive(completed_at, timezone=self.report.type.plan.tzinfo)
            append_to_key(_('Identifier'), action_identifier, 'identifier')
            append_to_key(_('Action'), action_name, 'name')
            for field in self.report.type.fields:
                labels = [label for label in field.block.xlsx_column_labels(field.value)]
                values = field.block.extract_action_values(
                    self, field.value, action.data, related_objects, attribute_versions
                )
                field_name = field.block.name
                if field_name == 'attribute_type':
                    field_name = f'{field_name}.{field.value.get("attribute_type").identifier}'
                assert len(labels) == len(values)
                self.formats.set_for_field(field, labels)
                for label, value in zip(labels, values):
                    append_to_key(label, value, field_name)
            append_to_key(COMPLETED_BY_LABEL, completed_by or '', 'completed_by')
            append_to_key(COMPLETED_AT_LABEL, completed_at, 'completed_at')
            self.formats.set_for_label(COMPLETED_AT_LABEL, self.formats.timestamp)

            if (visibility_label := action_obj.get_visibility_display()):
                append_to_key(_('Visibility'), visibility_label, 'visibility')

        if data and set(data.get(COMPLETED_AT_LABEL)) == {None}:
            if COMPLETED_AT_LABEL in data:
                del data[COMPLETED_AT_LABEL]
            if COMPLETED_BY_LABEL in data:
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
        if getattr(self.report.type.plan.features, 'output_report_action_print_layout', False):
            write_action_summaries(self, action_df)

        pivot_specs = [
            # Pivot sheet: Implementation phase
            {
                'group': (_('Implementation phase'),),
                'type': 'pie'
            },
            # Pivot sheet: Organization parent x Implementation phase
            {
                'group': (
                    pgettext('organization', 'Parent'),
                    _('Implementation phase')),
                'type': 'column'
            }
        ]

        # Pivot sheet: Category (level) x Implementation phase
        category_labels = self.report.type.get_field_labels_for_type('category')
        implementation_phase_fields = self.report.type.get_fields_for_type('implementation_phase')
        if len(implementation_phase_fields) > 0:
            for label in category_labels:
                assert len(label) == 1
                pivot_specs.append({
                    'group': (label[0], _('Implementation phase')),
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
            # The gradient is ugly on native Excel, some color design is needed before this should be enabled again
            #
            # chart.set_plotarea({
            #     'gradient': {'colors': ['#FFEFD1', '#F0EBD5', '#B69F66']}
            # })
            worksheet.insert_chart('A' + str(aggregated.height + 2), chart)

    def _initialize_format(self, key, initializer):
        format = self.workbook.add_format()
        self.formats[key] = format
        initializer(format)

    def _initialize_formats(self):
        for name, callback in inspect.getmembers(ExcelFormats.StyleSpecifications, inspect.ismethod):
            self._initialize_format(name, callback)
