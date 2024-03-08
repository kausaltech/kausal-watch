import pytest
from pytest_factoryboy import register

from factory import SubFactory

from reports.spreadsheets.action_print_layout import ReportActionPrintLayoutCustomization
from actions.tests.factories import PlanFactory
from aplans.factories import ModelFactory


pytestmark = pytest.mark.django_db


class ReportActionPrintLayoutCustomizationFactory(ModelFactory[ReportActionPrintLayoutCustomization]):
    plan = SubFactory(PlanFactory)
    max_columns=None,
    width_needed=None,
    approximate_chars_per_line=None,
    approximate_lines_per_page=None,
    min_split_chars=None



register(ReportActionPrintLayoutCustomizationFactory)


KEYS = ['max_columns', 'width_needed', 'approximate_chars_per_line', 'approximate_lines_per_page']


@pytest.fixture
def global_db_defaults():
    return ReportActionPrintLayoutCustomization.objects.get(plan=None)


def test_report_action_print_layout_customization_returns_db_defaults(plan, global_db_defaults):
    for key in KEYS:
        assert (
            ReportActionPrintLayoutCustomization.get_plan_variable_with_fallback(plan, key) ==
            getattr(global_db_defaults, key)
        )
        continue


def test_report_action_print_layout_customization_returns_plan_value_and_global_defaults(
        plan, global_db_defaults
):
    ReportActionPrintLayoutCustomization.save_plan_variable(plan, 'approximate_chars_per_line', 1000)
    for key in KEYS:
        if key == 'approximate_chars_per_line':
            assert ReportActionPrintLayoutCustomization.get_plan_variable_with_fallback(plan, key) == 1000
            continue
        assert ReportActionPrintLayoutCustomization.get_plan_variable_with_fallback(plan, key) == getattr(global_db_defaults, key)
