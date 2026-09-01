from io import BytesIO

from django.utils import translation
from django.utils.translation import gettext as _, pgettext

import polars as pl
import polars.selectors as cs
import pytest

from .fixtures import *

pl.Config.set_ascii_tables(True)
pl.Config.set_tbl_rows(20)
pl.Config.set_tbl_cols(20)

pytestmark = pytest.mark.django_db


@pytest.fixture
def excel_file_from_report_factory(actions_having_attributes, report_with_all_attributes):
    def _excel_factory(action_ids=None) -> bytes:
        assert report_with_all_attributes.type.plan.features.output_report_action_print_layout is True
        assert report_with_all_attributes.fields == report_with_all_attributes.type.fields
        exporter = report_with_all_attributes.get_xlsx_exporter(action_ids)
        output_excel = exporter.generate_xlsx()
        return output_excel

    return _excel_factory


def assert_report_dimensions(excel_file, report, actions):
    df_actions = pl.read_excel(BytesIO(excel_file), sheet_name=pgettext('Action model', 'Actions'), engine='openpyxl')
    non_report_fields = ['action', 'identifier']
    has_complete_actions = False
    if report.is_complete:
        has_complete_actions = True
    else:
        for a in actions:
            if a.is_complete_for_report(report):
                has_complete_actions = True
                break
    if has_complete_actions:
        non_report_fields.extend(['marked_as_complete_by', 'marked_as_complete_at'])

    # optional choice attribute results in two columns, hence + 1
    # responsible parties columns result in 3 columns, hence + 2
    assert df_actions.width == len(report.fields) + len(non_report_fields) + 1 + 2
    assert df_actions.height == len(actions)
    return df_actions


def test_excel_export(
    actions_having_attributes,
    report_with_all_attributes,
    excel_file_from_report_factory,
    user,
    django_assert_max_num_queries,
):
    with django_assert_max_num_queries(283):
        # report.get_live_action_versions hack still causes some extra queries
        # because of implementation details wrt. reversion
        excel_file_incomplete = excel_file_from_report_factory()

    df_incomplete = assert_report_dimensions(excel_file_incomplete, report_with_all_attributes, actions_having_attributes)
    report_with_all_attributes.mark_as_complete(user)

    with django_assert_max_num_queries(33):
        excel_file_complete = excel_file_from_report_factory()

    df_complete = assert_report_dimensions(excel_file_complete, report_with_all_attributes, actions_having_attributes)

    df_complete_minus_completion = None
    with translation.override(report_with_all_attributes.xlsx_exporter.language):
        df_complete_minus_completion = df_complete.select(
            cs.all() - cs.by_name(_('Marked as complete by'), _('Marked as complete at'))
        )
    assert df_incomplete.equals(df_complete_minus_completion)


def test_partly_completed_report_excel_export(
    actions_having_attributes, report_with_all_attributes, excel_file_from_report_factory, user
):
    actions_having_attributes[0].mark_as_complete_for_report(
        report_with_all_attributes,
        user,
    )
    excel = excel_file_from_report_factory()
    assert_report_dimensions(excel, report_with_all_attributes, actions_having_attributes)


def test_excel_export_action_filter(actions_having_attributes, report_with_all_attributes, excel_file_from_report_factory, user):
    actions_having_attributes[0].mark_as_complete_for_report(
        report_with_all_attributes,
        user,
    )
    included_actions = [actions_having_attributes[0], actions_having_attributes[1]]
    excel = excel_file_from_report_factory(action_ids=[a.id for a in included_actions])
    assert_report_dimensions(excel, report_with_all_attributes, included_actions)


def test_excel_export_with_duplicate_attribute_fields(
    plan,
    action_attribute_type__text,
    report_type_factory,
    report_factory,
    actions_having_attributes,
):
    """
    Test that duplicate attribute fields don't cause a ShapeError crash.

    Regression test for WATCH-BACKEND-3DJ: When a report type has the same
    attribute type configured twice, the Excel export would fail with:
    ShapeError: could not create a new DataFrame: height of column X does not match height of column Y

    The fix skips duplicate fields during DataFrame construction.
    """
    # Create a report type with the SAME attribute type added twice
    report_type = report_type_factory(
        plan=plan,
        fields__0='implementation_phase',
        fields__1__attribute__attribute_type=action_attribute_type__text,
        fields__2__attribute__attribute_type=action_attribute_type__text,  # Duplicate!
    )

    report = report_factory(type=report_type)
    report.fields = report_type.fields
    report.save()

    # This should NOT crash - duplicates should be skipped with a warning
    exporter = report.get_xlsx_exporter()
    excel_output = exporter.generate_xlsx()

    # Verify we got valid Excel output
    assert excel_output is not None
    assert len(excel_output) > 0

    # Verify the DataFrame was created successfully by reading it back
    df = pl.read_excel(BytesIO(excel_output), sheet_name=pgettext('Action model', 'Actions'), engine='openpyxl')
    assert df.height == len(actions_having_attributes)

    # The duplicate field should have been skipped, so we should have fewer columns
    # than if both fields were included
    # Expected: Identifier + Action + implementation_phase + 1 attribute (duplicate skipped)
    assert df.width == 4  # identifier, action name, impl phase, 1 attribute


def test_excel_export_with_duplicate_category_fields(
    plan,
    category_type,
    report_type_factory,
    report_factory,
    actions_having_attributes,
):
    """
    Test that duplicate category fields don't cause a ShapeError crash.

    Similar to test_excel_export_with_duplicate_attribute_fields but for category fields.
    """
    # Create a report type with the SAME category type added twice
    report_type = report_type_factory(
        plan=plan,
        fields__0='implementation_phase',
        fields__1__categories__category_type=category_type,
        fields__2__categories__category_type=category_type,  # Duplicate!
    )

    report = report_factory(type=report_type)
    report.fields = report_type.fields
    report.save()

    # This should NOT crash
    exporter = report.get_xlsx_exporter()
    excel_output = exporter.generate_xlsx()

    assert excel_output is not None
    df = pl.read_excel(BytesIO(excel_output), sheet_name=pgettext('Action model', 'Actions'), engine='openpyxl')
    assert df.height == len(actions_having_attributes)

    # Expected: Identifier + Action + implementation_phase + 1 category (duplicate skipped)
    assert df.width == 4


def test_report_type_validation_rejects_duplicate_fields(
    plan,
    action_attribute_type__text,
    report_type_factory,
):
    """
    Test that ReportType.clean() raises ValidationError for duplicate fields.

    This ensures that users cannot accidentally configure duplicate fields
    in the admin interface.
    """
    from django.core.exceptions import ValidationError

    report_type = report_type_factory(
        plan=plan,
        fields__0='implementation_phase',
        fields__1__attribute__attribute_type=action_attribute_type__text,
        fields__2__attribute__attribute_type=action_attribute_type__text,  # Duplicate!
    )

    with pytest.raises(ValidationError) as exc_info:
        report_type.clean()

    assert 'fields' in exc_info.value.message_dict
    assert 'Duplicate fields detected' in str(exc_info.value.message_dict['fields'])
