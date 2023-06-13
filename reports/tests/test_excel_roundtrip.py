from io import BytesIO

from django.utils.translation import gettext
import pytest
import polars


from .fixtures import *  # noqa


pytestmark = pytest.mark.django_db


@pytest.fixture
def dataframe_from_excel_factory(actions_having_attributes, report_with_all_attributes):
    def _return_sheet_as_dataframe(sheet_name: str):
        assert report_with_all_attributes.fields == report_with_all_attributes.type.fields
        output_excel = report_with_all_attributes.to_xlsx()
        return polars.read_excel(BytesIO(output_excel), sheet_name=sheet_name)
    return _return_sheet_as_dataframe


def test_excel_export(
        plan,
        actions_having_attributes,
        report_with_all_attributes,
        dataframe_from_excel_factory
):
    df_actions = dataframe_from_excel_factory(gettext('Actions'))
    non_report_fields = ['action', 'identifier']
    if report_with_all_attributes.is_complete:
        non_report_fields.extend(['marked_as_complete_by', 'marked_as_complete_at'])

    # optional choice attribute results in two columns, hence + 1
    assert df_actions.width == len(report_with_all_attributes.fields) + len(non_report_fields) + 1
    assert df_actions.height == len(actions_having_attributes)
