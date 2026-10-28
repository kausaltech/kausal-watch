"""The report comparison block compares the reports chosen in it (plan 3, Phase C)."""

from __future__ import annotations

import datetime
import importlib
import json

from django.apps import apps as django_apps
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.models import Revision

import pytest

from admin_site.tests.factories import ClientPlanFactory
from pages.models import ActionListPage
from reports.blocks.report_comparison_block import ReportComparisonBlock
from reports.tests.factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db

fill_migration = importlib.import_module('pages.migrations.0076_fill_report_comparison_reports')


@pytest.fixture
def report_type(plan_with_pages):
    return ReportTypeFactory.create(plan=plan_with_pages)


@pytest.fixture
def action_list_page(plan_with_pages) -> ActionListPage:
    page = plan_with_pages.get_action_list_page()
    assert page is not None
    return page


def _report(report_type, name: str, year: int, is_complete=True):
    return ReportFactory.create(
        type=report_type,
        name=name,
        start_date=datetime.date(year, 1, 1),
        end_date=datetime.date(year, 12, 31),
        is_complete=is_complete,
    )


def _block_value(block: ReportComparisonBlock, report_type, reports):
    return block.to_python({
        'report_type': report_type.pk,
        'reports': [report.pk for report in reports],
        'report_field': 'some-uuid',
    })


def test_compares_the_chosen_reports_in_the_chosen_order(report_type):
    block = ReportComparisonBlock()
    older = _report(report_type, '2024', 2024)
    newer = _report(report_type, '2025', 2025)
    _report(report_type, 'Not chosen', 2023)

    value = _block_value(block, report_type, [older, newer])
    assert block.reports_to_compare(None, value) == [older, newer]


def test_skips_chosen_reports_that_have_been_deleted(report_type):
    block = ReportComparisonBlock()
    kept = _report(report_type, 'Kept', 2024)
    deleted = _report(report_type, 'Deleted', 2025)
    deleted_pk = deleted.pk
    deleted.delete()
    deleted.pk = deleted_pk

    value = _block_value(block, report_type, [kept, deleted])
    assert block.reports_to_compare(None, value) == [kept]


def test_refuses_a_report_of_another_template(plan_with_pages, report_type):
    block = ReportComparisonBlock()
    other = _report(ReportTypeFactory.create(plan=plan_with_pages), 'Other', 2025)

    with pytest.raises(StructBlockValidationError):
        block.clean(_block_value(block, report_type, [other]))


def test_refuses_an_open_report(report_type):
    block = ReportComparisonBlock()
    open_report = _report(report_type, 'Open', 2026, is_complete=False)

    with pytest.raises(StructBlockValidationError):
        block.clean(_block_value(block, report_type, [open_report]))


def test_accepts_completed_reports_of_the_template(report_type):
    block = ReportComparisonBlock()
    report = _report(report_type, '2025', 2025)

    assert list(block.clean(_block_value(block, report_type, [report]))['reports']) == [report]


def test_chooser_offers_the_completed_reports_of_the_active_plan(client, plan_with_pages, plan_admin_user, report_type):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    _report(report_type, 'Completed report', 2025)
    _report(report_type, 'Open report', 2026, is_complete=False)
    _report(ReportTypeFactory.create(), 'Report of another plan', 2025)

    content = client.get('/admin/report-chooser/').content.decode()
    assert 'Completed report' in content
    assert 'Open report' not in content
    assert 'Report of another plan' not in content


def _old_block(report_type_id) -> dict:
    """Return a report comparison block as it was stored before it listed its reports."""
    return {
        'type': 'report_comparison',
        'value': {'report_type': report_type_id, 'report_field': 'some-uuid'},
        'id': 'block-id',
    }


def _filler(report_pks_by_type: dict[int, list[int]]):
    # `Report.is_public` is gone from the current model, so give the migration the reports it would have looked up
    filler = fill_migration.ReportComparisonFiller(django_apps)
    filler.report_pks_by_type = report_pks_by_type
    return filler


def test_migration_fills_blocks_with_the_reports_they_showed(action_list_page, report_type):
    newer = _report(report_type, '2025', 2025)
    older = _report(report_type, '2024', 2024)
    ActionListPage.objects.filter(pk=action_list_page.pk).update(details_main_bottom=[_old_block(report_type.pk)])

    fill_migration.fill_pages(django_apps, _filler({report_type.pk: [newer.pk, older.pk]}))

    page = ActionListPage.objects.get(pk=action_list_page.pk)
    assert page.details_main_bottom is not None
    value = page.details_main_bottom[0].value
    assert list(value['reports']) == [newer, older]
    assert value['report_type'] == report_type


def test_migration_fills_blocks_in_drafts(action_list_page, report_type):
    report = _report(report_type, '2025', 2025)
    revision = action_list_page.save_revision()
    revision.content['details_main_top'] = '[]'
    revision.content['details_main_bottom'] = json.dumps([_old_block(report_type.pk)])
    revision.save()

    fill_migration.fill_revisions(django_apps, _filler({report_type.pk: [report.pk]}))

    draft = Revision.objects.get(pk=revision.pk).as_object()
    assert list(draft.details_main_bottom[0].value['reports']) == [report]


def test_migration_leaves_blocks_that_list_their_reports(action_list_page, report_type):
    block = {**_old_block(report_type.pk)}
    block['value'] = {**block['value'], 'reports': []}
    filler = _filler({report_type.pk: [1]})

    assert not filler.fill([block])
    assert block['value']['reports'] == []
