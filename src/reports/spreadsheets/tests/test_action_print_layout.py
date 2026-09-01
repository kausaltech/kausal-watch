import pytest
from factory import SubFactory
from pytest_factoryboy import register

from aplans.factories import ModelFactory

from actions.models import Plan
from actions.tests.factories import PlanFactory
from reports.spreadsheets.action_print_layout import ReportActionPrintLayoutCustomization

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
