from __future__ import annotations

import pathlib
import typing
from io import BytesIO
from typing import Any, Iterable, Sequence

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone, translation
from django.utils.text import slugify
from django.utils.translation import gettext as _, pgettext
from reversion.models import Version

import polars as pl
import xlsxwriter
from loguru import logger

from actions.models.action import Action, ActionImplementationPhase, ActionStatus
from orgs.models import Organization
from reports.utils import ReportCellValue, group_by_model

from .action_print_layout import write_action_summaries
from .cursor_writer import Cell, CursorWriter
from .excel_formats import ExcelFormats

if typing.TYPE_CHECKING:
    from django.db.models import Model, QuerySet

    from actions.models.category import Category, CategoryType
    from actions.models.plan import Plan
    from reports.models import Report
    from reports.types import SerializedActionVersion, SerializedVersion


def clean(value: ReportCellValue) -> ReportCellValue:
    r"""Translate Windows linefeeds to \n for Excel."""
    if not isinstance(value, str):
        return value
    return value.replace("\r\n", "\n")


# T = TypeVar('T')


class ExcelReport:
    language: str
    report: Report
    workbook: xlsxwriter.Workbook
    formats: ExcelFormats
    plan_current_related_objects: PlanRelatedObjects
    field_to_column_labels: dict[str, set[str]]
    has_macros: bool
    plan: Plan
    action_ids: list[int] | None  # if not None, restrict to these actions
    child_plans: list[Plan]
    # Is this report and its type dynamically created
    # (not loaded from database)
    is_dynamic: bool

    class PlanRelatedObjects:
        implementation_phases: dict[int, ActionImplementationPhase]
        organizations: dict[int, Organization]
        categories: dict[int, Category]
        category_types: dict[int, CategoryType]
        statuses: dict[int, ActionStatus]
        action_content_type: ContentType

        def __init__(self, report: Report, child_plans: list[Plan] | None = None):
            plan = report.type.plan
            if child_plans is None:
                child_plans = []
            self.category_types = self._keyed_dict(plan.category_types.all())
            self.categories = self._keyed_dict([c for ct in self.category_types.values() for c in ct.categories.all()])
            self.implementation_phases = self._keyed_dict(plan.action_implementation_phases.all())
            self.statuses = self._keyed_dict(plan.action_statuses.all())
            self.organizations = self._keyed_dict(Organization.objects.available_for_plan(plan))
            self.action_content_type = ContentType.objects.get_for_model(Action)
            # Aggregate related objects from child plans
            for child_plan in child_plans:
                self.category_types.update(self._keyed_dict(child_plan.category_types.all()))
                self.categories.update(self._keyed_dict([c for ct in self.category_types.values() for c in ct.categories.all()]))
                self.implementation_phases.update(self._keyed_dict(child_plan.action_implementation_phases.all()))
                self.statuses.update(self._keyed_dict(child_plan.action_statuses.all()))
                self.organizations.update(self._keyed_dict(Organization.objects.available_for_plan(child_plan)))

            self.category_level_category_mappings = {
                ct.pk: ct.categories_projected_by_level() for ct in self.category_types.values()
            }

        @staticmethod
        def _keyed_dict[T: Model](seq: Iterable[T]) -> dict[int, T]:
            return {el.pk: el for el in seq}

    def __init__(self, report: Report, language: str|None = None, is_dynamic: bool = False, action_ids: list[int] | None = None):
        # Currently only language None is properly supported, defaulting
        # to the plan's primary language. When implementing support for
        # other languages, make sure the action contents and other
        # plan object contents are translated.

        self.language = report.type.plan.primary_language if language is None else language
        self.report = report
        self.is_dynamic = is_dynamic
        self.output = BytesIO()
        self.workbook = xlsxwriter.Workbook(
            self.output,
            {
                'in_memory': True,
            }
        )
        self.formats = ExcelFormats(self.workbook)
        self.plan = self.report.type.plan
        self.action_ids = action_ids
        if report.type.plan.features.output_report_action_print_layout and not report.disable_macros:
            # add macro to enable post-processing in Excel
            self.workbook.add_vba_project(pathlib.Path(__file__).parent / 'vbaProject.bin')
            self.has_macros = True
        else:
            self.has_macros = False

        if (child_plans := report.type.plan.children.get_queryset().prefetch_related(
                'category_types', 'action_implementation_phases', 'action_statuses', 'related_organizations')) and \
                report.type.get_action_list_page().include_related_plans:
            self.child_plans = list(child_plans)  # TODO: add .visible_for_user() when it is implemented
            self.plan_current_related_objects = self.PlanRelatedObjects(self.report, self.child_plans)
        else:
            self.child_plans = []
            self.plan_current_related_objects = self.PlanRelatedObjects(self.report)
        self.field_to_column_labels = dict()

    def get_filename(self, suffix: str | None = None) -> str:
        if suffix is None:
            suffix = '.xlsm' if self.has_macros else '.xlsx'
        return slugify(self.report.name, allow_unicode=True) + suffix

    def generate_actions_dataframe(self) -> pl.DataFrame:
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

    def generate_csv(self) -> str:
        actions_df = self.generate_actions_dataframe()
        with translation.override(self.language):
            return actions_df.write_csv()

    def _write_title_sheet(self) -> None:
        if self.report.disable_title_sheet:
            return
        worksheet = self.workbook.add_worksheet(_('Lead'))
        plan = self.report.type.plan
        start = self.report.start_date
        end = self.report.end_date
        complete_key = _('status')
        complete_label = _('complete')
        not_complete_label = _('in progress')
        completed = complete_label if self.report.is_complete else not_complete_label
        datetime_now = timezone.make_naive(timezone.now(), timezone=self.report.type.plan.tzinfo)
        cells: Sequence[Sequence[Cell]] = [
            [Cell(plan.name, 'title')],
            [Cell(self.report.type.name, 'sub_title')],
            [Cell(self.report.name, 'sub_sub_title')],
            [],
            [Cell(complete_key, 'metadata_label'), Cell(completed, 'metadata_value')],
            [Cell(str(self.report._meta.get_field('start_date').verbose_name), 'metadata_label'), Cell(start, 'date')],
            [Cell(str(self.report._meta.get_field('end_date').verbose_name), 'metadata_label'), Cell(end, 'date')],
            [Cell(_('updated at'), 'metadata_label'), Cell(datetime_now, 'date')],
            [],
            [Cell(_('Exported from Kausal Watch'), 'metadata_value')],
            [Cell('kausal.tech', 'metadata_value', url='https://kausal.tech')],
            [],
        ]
        CursorWriter(
            worksheet,
            formats=self.formats,
            default_format=self.formats.even_row,
            width=3,
        ).write_cells(cells)
        worksheet.set_row(0, 30)
        worksheet.set_row(1, 30)
        worksheet.set_row(2, 30)
        worksheet.autofit()
        worksheet.set_column(1, 1, 40)

    def _write_actions_sheet(self, df: pl.DataFrame) -> xlsxwriter.worksheet.Worksheet:
        return self._write_sheet(self.workbook.add_worksheet(_('Actions')), df)

    def _write_sheet(
            self,
            worksheet: xlsxwriter.worksheet.Worksheet,
            df: pl.DataFrame,
            small: bool = False,
    ) -> xlsxwriter.worksheet.Worksheet:

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
            _format = self.formats.get_for_label(label)
            if _format is None:
                _format = self.formats.all_rows
            width: int | None = col_width
            if i == 0:
                width = first_col_width
            elif i == len(df.columns) - 1:
                width = last_col_width
            if small:
                width = None
            worksheet.set_column(i, i, width, _format)
            i += 1
        worksheet.conditional_format(1, 0, df.height, df.width-1, {
            'type': 'formula',
            'criteria': '=MOD(ROW(),2)=0',
            'format': self.formats.odd_row,
        })
        worksheet.conditional_format(1, 0, df.height, df.width-1, {
            'type': 'formula',
            'criteria': '=NOT(MOD(ROW(),2)=0)',
            'format': self.formats.even_row,
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
        from reports.types import SerializedActionVersion, SerializedVersion
        if self.report.is_complete:
            serialized_actions: list[SerializedActionVersion] = []
            snapshots = self.report.action_snapshots.all()
            if self.action_ids is not None:
                snapshots.filter(action_version__object_id__in=self.action_ids)
            snapshots = (
                snapshots
                .select_related('action_version__revision__user')
                .prefetch_related('action_version__revision__version_set')
            )
            related_versions: QuerySet[Version] = Version.objects.none()
            for snapshot in snapshots:
                action_version_data = snapshot.get_serialized_data()
                serialized_actions.append(action_version_data)
                related_versions |= snapshot.get_related_versions()
            serialized_related = [SerializedVersion.from_version_polymorphic(v) for v in related_versions]
            serialized_actions = sorted(serialized_actions, key=lambda x: x.data['order'])
            return serialized_actions, serialized_related

        # Live incomplete report, although some actions might be completed for report
        live_versions = self.report.get_live_versions(action_ids=self.action_ids)
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
        from reports.types import SerializedAttributeVersion
        data: dict[str, list[Any]] = {}

        def append_to_key(key: str, value: ReportCellValue, field_name: str) -> None:
            self.field_to_column_labels.setdefault(field_name, set()).add(key)
            data.setdefault(key, []).append(value)

        completed_by_label = _('Marked as complete by')
        completed_at_label = _('Marked as complete at')

        related_objects = group_by_model(all_related_versions)
        attribute_versions = {
            v.attribute_path: v
            for v in all_related_versions
            if isinstance(v, SerializedAttributeVersion)
        }

        fields = []
        for field in self.report.type.fields:
            if field is not None and field.value is not None and 'attribute_type' in field.value and \
                    field.value['attribute_type'] is None:
                logger.error(f"Field has NoneType attribute_type in report type {self.report.type.name}.")
                continue
            fields.append(field)
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
            if self.child_plans:
                append_to_key(_('Plan'), action_obj.plan.name, 'plan')
            for field in fields:
                labels = list(field.block.xlsx_column_labels(field.value, plan=self.report.type.plan))
                values = field.block.extract_action_values(
                    self, field.value, action.data, related_objects, attribute_versions,
                )
                field_name = field.block.name
                if field_name == 'attribute_type':
                    field_name = f'{field_name}.{field.value.get("attribute_type").identifier}'
                assert len(labels) == len(values)
                self.formats.set_for_field(field, labels)
                values = [clean(v) for v in values]
                for label, value in zip(labels, values, strict=False):
                    append_to_key(label, value, field_name)
            append_to_key(completed_by_label, completed_by or '', 'completed_by')
            append_to_key(completed_at_label, completed_at, 'completed_at')
            self.formats.set_for_label(completed_at_label, self.formats.timestamp)
        if data and set(data.get(completed_at_label) or [None]) == {None}:
            if completed_at_label in data:
                del data[completed_at_label]
            if completed_by_label in data:
                del data[completed_by_label]
        return pl.DataFrame(data)

    def _get_aggregates(self, labels: Sequence[str], action_df: pl.DataFrame) -> pl.DataFrame | None:
        for label in labels:
            if label not in action_df.columns:
                return None
        if len(labels) == 0 or len(labels) > 2:
            raise ValueError('Only one or two dimensional pivot tables supported')
        action_df = action_df.fill_null('[' + _('Unknown') + ']')
        if len(labels) == 1:
            return (action_df
                    .group_by(labels)
                    .len()
                    .rename({'len': _('Actions')}))
        return action_df.pivot(  # noqa: PD010
            values=_("Identifier"),
            index=labels[0],
            on=labels[1],
            aggregate_function="len",
            ).sort(labels[0])

    def post_process(self, action_df: pl.DataFrame):
        if self.report.disable_summary_sheets:
            return
        if getattr(self.report.type.plan.features, 'output_report_action_print_layout', False):
            write_action_summaries(self, action_df)

        pivot_specs = [
            # Pivot sheet: Implementation phase
            {
                'group': (_('Implementation phase'),),
                'type': 'pie',
            },
            # Pivot sheet: Organization parent x Implementation phase
            {
                'group': (
                    pgettext('organization', 'Parent'),
                    _('Implementation phase')),
                'type': 'column',
            },
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
                    'subtype': 'stacked',
                })
        sheet_number = 1

        def is_column_data_missing(field_label: str) -> bool:
            return field_label not in action_df or action_df.get_column(field_label).dtype.is_(pl.datatypes.Null)

        for spec in pivot_specs:
            grouping = spec['group']
            if any(is_column_data_missing(field_label) for field_label in grouping):
                continue

            aggregated = self._get_aggregates(grouping, action_df)
            if aggregated is None:
                continue
            sheet_name = _("Summary") + f" {sheet_number}"
            sheet_number += 1
            worksheet = self.workbook.add_worksheet(sheet_name)
            self._write_sheet(worksheet, aggregated, small=True)
            chart_type = spec['type']
            chart = self.workbook.add_chart({'type': chart_type, 'subtype': spec.get('subtype')})
            for i in range(aggregated.width - 1):
                series = {
                    'categories': [sheet_name, 1, 0, aggregated.height, 0],
                    'values': [sheet_name, 1, 1 + i, aggregated.height, 1 + i],
                    'name': [sheet_name, 0, 1 + i],
                }
                chart.add_series(series)
            if chart_type == 'column':
                chart.set_size({'width': 720, 'height': 576})
            worksheet.insert_chart('A' + str(aggregated.height + 2), chart)
