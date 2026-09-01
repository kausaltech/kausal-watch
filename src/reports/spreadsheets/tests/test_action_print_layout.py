import pytest
from factory import SubFactory
from pytest_factoryboy import register

from aplans.factories import ModelFactory

from actions.models import Plan
from actions.tests.factories import PlanFactory
from reports.spreadsheets.action_print_layout import ReportActionPrintLayoutCustomization, _build_grid_layout

pytestmark = pytest.mark.django_db


class ReportActionPrintLayoutCustomizationFactory(ModelFactory[ReportActionPrintLayoutCustomization]):
    plan = SubFactory[ReportActionPrintLayoutCustomization, Plan](PlanFactory)
    max_columns: int | None = None
    width_needed: list[list[int]] | None = None
    approximate_chars_per_line: int | None = None
    approximate_lines_per_page: int | None = None
    min_split_chars: int | None = None


register(ReportActionPrintLayoutCustomizationFactory)


KEYS = ['max_columns', 'width_needed', 'approximate_chars_per_line', 'approximate_lines_per_page']


@pytest.fixture
def global_db_defaults():
    return ReportActionPrintLayoutCustomization.objects.get(plan=None)


def test_report_action_print_layout_customization_returns_db_defaults(plan, global_db_defaults):
    for key in KEYS:
        assert ReportActionPrintLayoutCustomization.get_plan_variable_with_fallback(plan, key) == getattr(global_db_defaults, key)
        continue


def test_report_action_print_layout_customization_returns_plan_value_and_global_defaults(
    plan,
    global_db_defaults,
):
    ReportActionPrintLayoutCustomization.save_plan_variable(plan, 'approximate_chars_per_line', 1000)
    for key in KEYS:
        if key == 'approximate_chars_per_line':
            assert ReportActionPrintLayoutCustomization.get_plan_variable_with_fallback(plan, key) == 1000
            continue
        assert ReportActionPrintLayoutCustomization.get_plan_variable_with_fallback(plan, key) == getattr(global_db_defaults, key)


class TestBuildGridLayout:
    """
    Regression tests for the empty-row condition behind the 2026-09-01 de-prod incident.

    An empty row in the grid layout made `grid_layout_to_grid_values` spin forever on
    the same index, pegging a worker thread that nothing cancels when the client
    disconnects. `_build_grid_layout` must therefore never emit one.
    """

    MAX_COLUMNS = 4

    def test_packs_labels_into_rows(self):
        rows = _build_grid_layout([('a', 2), ('b', 2), ('c', 2)], filter_out=[], max_columns=self.MAX_COLUMNS)
        assert rows == [['a', 'b'], ['c']]

    def test_all_labels_filtered_out_yields_no_rows(self):
        rows = _build_grid_layout(
            [('identifier', 2), ('name', 2)],
            filter_out=['identifier', 'name'],
            max_columns=self.MAX_COLUMNS,
        )
        assert rows == []

    def test_field_wider_than_a_row_does_not_emit_a_leading_empty_row(self):
        rows = _build_grid_layout([('wide', 8), ('a', 2)], filter_out=[], max_columns=self.MAX_COLUMNS)
        assert [] not in rows
        assert rows == [['wide'], ['a']]

    def test_no_input_yields_no_rows(self):
        assert _build_grid_layout([], filter_out=[], max_columns=self.MAX_COLUMNS) == []

    @pytest.mark.parametrize(
        'keys_to_column_count',
        [
            [],
            [('identifier', 2)],
            [('identifier', 2), ('name', 2)],
            [('wide', 99), ('identifier', 2)],
            [('a', 2), ('identifier', 2), ('b', 4), ('c', 4)],
        ],
    )
    def test_never_emits_an_empty_row(self, keys_to_column_count):
        rows = _build_grid_layout(
            keys_to_column_count,
            filter_out=['identifier', 'name'],
            max_columns=self.MAX_COLUMNS,
        )
        assert all(row for row in rows)
