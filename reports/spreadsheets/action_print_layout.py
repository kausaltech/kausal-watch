"""A module for writing action data in  a spreadsheet in a format which aims to
fit a visually pleasing  amount of data in one printed page  of the sheet. This
module writes explicit horizontal page breaks with worksheet.set_h_pagebreaks()

The internal implementation  is considered a hack based on  heuristics and lots
of trial-and-error. The implementation uses a lot of magic numbers which can be
tweaked per plan in the database in order to avoid having to deploy the code if
some assumptions are different for different  plans. The reason for all this is
the fact  that there seems  to be no way  to accurately pinpoint  the locations
where the page breaks should be output.

In the end it  would be nice to find a sustainable solution  to replace some of
the rough estimations happening here.

"""
from __future__ import annotations
from dataclasses import dataclass
from functools import reduce
from loguru import logger
import re
from typing import Any, cast
import typing

from django.utils.translation import gettext as _
from django.db import models

from .cursor_writer import CursorWriter, CellBase, Cell

if typing.TYPE_CHECKING:
    import polars
    from .excel_report import ExcelReport
    from actions.models import Plan


class ReportActionPrintLayoutCustomization(models.Model):
    # If plan is None, this acts as a global fallback for defaults
    plan = models.OneToOneField('actions.Plan', on_delete=models.CASCADE, related_name='+', null=True, blank=True)
    max_columns = models.IntegerField(null=True, blank=True)
    approximate_chars_per_line = models.IntegerField(null=True, blank=True)
    approximate_lines_per_page = models.IntegerField(null=True, blank=True)
    min_split_chars = models.IntegerField(null=True, blank=True)
    # Approximately how many excel columns do we need to fit a string of this many characters.  4 is full width, 2 is half of the width of
    # the entire page.
    # Contains a list[list[int, int]]
    # (fist of pair is char count, second width in columns)
    width_needed = models.JSONField(null=True, blank=True)

    @classmethod
    def _get_field_names(cls) -> list[str]:
        return [f.name for f in cls._meta.get_fields() if f.name not in ('plan', 'id')]

    @classmethod
    def get_plan_variable_with_fallback(cls, plan: Plan, key: str) -> Any:
        cls._validate_key(key)
        values = cls.get_plan_variables_with_fallback(plan)
        return getattr(values, key)

    @classmethod
    def get_plan_variables_with_fallback(cls, plan: Plan) -> ReportActionPrintLayoutCustomization:
        instance, fallback = cls._get_instance_with_fallback(plan)
        assert fallback is not None
        values = fallback
        if instance is None:
            return values
        for field_name in cls._get_field_names():
            value = getattr(instance, field_name)
            if value:
                setattr(values, field_name, value)
        return values

    @classmethod
    def save_plan_variable(cls, plan: Plan, key: str, value: int) -> ReportActionPrintLayoutCustomization:
        cls._validate_key(key)
        instance, _ = cls.objects.get_or_create(plan=plan)
        setattr(instance, key, value)
        instance.save()
        return instance

    @classmethod
    def save_plan_variables(cls, plan: Plan | None, variables: dict[str, Any]) -> None:
        field_names = cls._get_field_names()
        instance, _ = cls.objects.get_or_create(plan=plan)
        for key, value in variables.items():
            if key not in field_names:
                raise ValueError(f'Unsupported variable key {key}')
            setattr(instance, key, value)
        instance.save()

    @classmethod
    def _validate_key(cls, key: str) -> None:
        if key not in cls._get_field_names():
            raise ValueError(f'Unsupported variable key {key}')

    @classmethod
    def _get_instance_with_fallback(cls, plan: Plan) -> (
            tuple[ReportActionPrintLayoutCustomization | None,
                  ReportActionPrintLayoutCustomization | None]
    ):
        instance = cls.objects.filter(plan=plan)
        fallback = cls.objects.filter(plan=None)
        return (instance.get() if instance else None), (fallback.get() if fallback else None)


def _keys_with_total_length(action_df: polars.DataFrame) -> list[tuple[str, int]]:
    result = []
    d = action_df.to_dict()
    def reducer(x: int, y: str) -> int:
        return max(x, (len(str(y)) if y is not None else 0))
    for label, datas in d.items():
        result.append((label, reduce(reducer, datas, 0)))
    return result


@dataclass
class NewPageMarker(CellBase):
    action_identifier: str
    action_name: str
    def is_page_break(self) -> bool:
        return True


def write_action_summaries(excel_report: ExcelReport, action_df: polars.DataFrame) -> None:
    keys_with_total_length = _keys_with_total_length(action_df)

    plan = excel_report.report.type.plan
    custom_variables = ReportActionPrintLayoutCustomization.get_plan_variables_with_fallback(plan)
    MAX_COLUMNS = custom_variables.max_columns
    WIDTH_NEEDED: list[list[int | None]] = custom_variables.width_needed
    APPROXIMATE_CHARS_PER_LINE = custom_variables.approximate_chars_per_line
    APPROXIMATE_LINES_PER_PAGE = custom_variables.approximate_lines_per_page
    MIN_SPLIT_CHARS = custom_variables.min_split_chars

    if (
            MAX_COLUMNS is None or
            APPROXIMATE_CHARS_PER_LINE is None or
            APPROXIMATE_LINES_PER_PAGE is None or
            MIN_SPLIT_CHARS is None or
            WIDTH_NEEDED is None or not WIDTH_NEEDED or len(WIDTH_NEEDED) < 1 or len(WIDTH_NEEDED[0]) != 2
    ):
        logger.error(f'Invalid custom_variables received for write_action_summaries, pk: {custom_variables.pk}')
        return

    assert isinstance(MAX_COLUMNS, int)
    assert isinstance(APPROXIMATE_LINES_PER_PAGE, int)
    assert isinstance(MIN_SPLIT_CHARS, int)

    def map_length(length: int) -> list[int | None]:
        try:
            return next(w for w in WIDTH_NEEDED if (w[0] is not None and w[0] >= length))
        except StopIteration:
            return [None, MAX_COLUMNS]

    def get_single_field_label(field_name: str) -> str:
        labels = excel_report.get_column_labels(field_name).copy()
        assert len(labels) == 1
        val: str = labels.pop()
        return val

    FILTER_OUT_FIELDS = ('identifier', 'name', 'completed_by', 'completed_at')
    FILTER_OUT = [get_single_field_label(f) for f in FILTER_OUT_FIELDS]

    keys_to_column_count: list[tuple[str, int | None]] = [
        (label, map_length(length)[1]) for label, length in keys_with_total_length
    ]
    grid_layout: list[list[str]] = []
    current_row: list[str] = []
    cols_left_in_row = MAX_COLUMNS
    for label, cols in keys_to_column_count:
        if label in FILTER_OUT:
            continue
        assert cols is not None
        if cols > cols_left_in_row:
            grid_layout.append(current_row)
            current_row = []
            cols_left_in_row = MAX_COLUMNS
        current_row.append(label)
        cols_left_in_row -= cols
    grid_layout.append(current_row)

    def pop_value_from_action(action: dict[str, Any], field_name: str) -> Any:
        label = get_single_field_label(field_name)
        val = action[label]
        del action[label]
        return val

    pages_per_action_identifier = {}
    def grid_layout_to_grid_values(
            grid_layout: list[list[str]],
            action: dict[str, Any],
            approximate_chars_per_line: int,
            approximate_lines_per_page: int
    ) -> list[tuple[CellBase, ...]]:

        result: list[tuple[CellBase, ...]] = []
        action_identifier = pop_value_from_action(action, 'identifier')
        action_name = pop_value_from_action(action, 'name')
        pages_per_action_identifier[action_identifier] = 1
        result.append((NewPageMarker(action_identifier, action_name), ))

        def style_for_value(val: str | None) -> str:
            if val is not None and len(str(val)) > 100:
                return 'action_digest_value_long'
            return 'action_digest_value'

        def clean_text(val: str) -> str:
            val = str(val).replace("\n\n", "\n")
            return val.rstrip()

        approximate_lines_so_far = 0
        label_row: tuple[Cell, ...] = tuple()
        value_row: tuple[Cell, ...] = tuple()

        i = 0
        while i < len(grid_layout):
            if not label_row:
                row = grid_layout[i]
                label_row = tuple(Cell(label, 'action_digest_label') for label in row if label not in FILTER_OUT)
                value_row = tuple(Cell(clean_text(action.get(label) or '-'), style_for_value(action.get(label)))
                                  for label in row if label not in FILTER_OUT)

            accumulated_string_contents = "\n".join([str(x.value) for x in value_row])
            total_len_chars = reduce(lambda x,y: x + y, [len(str(x.value)) for x in value_row], 0)

            approximate_lines_so_far += 1 # header

            assert len(label_row) == len(value_row)
            if len(label_row) == 0:
                label_row = tuple()
                continue

            if len(label_row) == 1:
                approximate_lines_so_far += int(total_len_chars / approximate_chars_per_line)
                newline_count = len(re.findall(r"\n", accumulated_string_contents))
                approximate_lines_so_far += newline_count
            else:
                approximate_lines_so_far += 2

            MIN_SPLIT_CHARS = 500

            if approximate_lines_so_far > approximate_lines_per_page:
                last_element_value = value_row[-1].value
                approximate_lines_last_el = int(len(last_element_value)/approximate_chars_per_line)
                approximate_lines_last_el += len(re.findall(r"\n", last_element_value))

                delta = approximate_lines_per_page - (approximate_lines_so_far - approximate_lines_last_el)
                delta = delta * approximate_chars_per_line
                split_point = delta
                if split_point > len(last_element_value) - 1:
                    split_point = int(len(last_element_value)/2)
                if split_point < MIN_SPLIT_CHARS:
                    split_point = min(len(last_element_value)-1, MIN_SPLIT_CHARS)
                if split_point < 0:
                    split_point = 0
                while split_point > 0 and not re.match(r'\s', last_element_value[split_point]):
                    split_point -= 1
                    if split_point < MIN_SPLIT_CHARS and re.match(r'\s', last_element_value[split_point]):
                        break
                split_point += 1
                part1 = last_element_value[0:split_point]
                part2 = last_element_value[split_point:]
                result.append(label_row)
                if len(part2) < approximate_chars_per_line / 2:
                    result.append(value_row[0:-1] + (Cell(last_element_value, 'action_digest_value_long'),))
                    if i + 1 < len(grid_layout):
                        result.append((NewPageMarker(action_identifier, action_name),))
                        pages_per_action_identifier[action_identifier] += 1
                        approximate_lines_so_far = 0
                    label_row = tuple()
                    i += 1
                else:
                    result.append(value_row[0:-1] + (Cell(part1, 'action_digest_value_long'),))
                    result.append((NewPageMarker(action_identifier, action_name),))
                    pages_per_action_identifier[action_identifier] += 1
                    approximate_lines_so_far = 0
                    value_row = (Cell(part2, value_row[-1].format), )
            else:
                result.append(label_row)
                result.append(value_row)
                label_row = tuple()
                i += 1
        return result

    sheet_rows = []
    for data_row in action_df.iter_rows(named=True):
        sheet_rows.extend(
            grid_layout_to_grid_values(
                grid_layout,
                data_row,
                APPROXIMATE_CHARS_PER_LINE,
                APPROXIMATE_LINES_PER_PAGE,
            )
        )

    page_break_row_indexes = []
    row_index = 0
    processed: list[tuple[Cell, ...]] = []
    page = 1
    last_action_identifier = None

    for sheet_row in sheet_rows:
        if all(not x.is_page_break() for x in sheet_row):
            # Safe to cast because page breaks and normal cells are mutually exhaustive
            sheet_row = cast(tuple[Cell, ...], sheet_row)
            processed.append(sheet_row)
            row_index += 1
            continue

        cell = cast(NewPageMarker, sheet_row[0])
        action_identifier = cell.action_identifier
        action_name = cell.action_name
        assert isinstance(action_identifier, str)
        if action_identifier == last_action_identifier:
            page += 1
        else:
            last_action_identifier = action_identifier
            page = 1
        assert isinstance(action_name, str)
        if row_index != 0:
            page_break_row_indexes.append(row_index)
        page_specifier = ''
        page_count = pages_per_action_identifier[action_identifier]
        if page_count > 1:
            page_specifier = f' [{_("Page")} {page}/{page_count}]'
        processed.append((
            Cell(value=(action_identifier + page_specifier), format='action_digest_page_header'),
            Cell(value=action_name, format='action_digest_page_header')
        ))
        row_index += 1

    worksheet = excel_report.workbook.add_worksheet(_('Paginated actions'))
    worksheet.set_column(0, MAX_COLUMNS - 1, 16)
    cursor_writer = CursorWriter(
        worksheet,
        formats=excel_report.formats,
        width=MAX_COLUMNS,
        merge=True
    )
    cursor_writer.write_cells(processed)
    worksheet.set_h_pagebreaks(page_break_row_indexes)
