"""The report comparison block compares the reports chosen in it (plan 3, Phase C)."""

from __future__ import annotations

import datetime
import importlib
import json

from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from wagtail.blocks.struct_block import StructBlockValidationError
from wagtail.models import Revision

import pytest

from actions.models import Action, AttributeType
from actions.tests.factories import AttributeTypeFactory
from admin_site.tests.factories import ClientPlanFactory
from pages.models import ActionListPage
from reports.blocks.choosers import ReportTypeFieldSelect
from reports.blocks.report_comparison_block import ReportComparisonBlock, comparable_fields
from reports.tests.factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db

fill_migration = importlib.import_module('pages.migrations.0076_fill_report_comparison_reports')


PUBLIC_FIELD = '6b0c1d2e-0000-4000-8000-000000000001'
LOGGED_IN_FIELD = '6b0c1d2e-0000-4000-8000-000000000002'
BUILT_IN_FIELD = '6b0c1d2e-0000-4000-8000-000000000003'
TASKS_FIELD = '6b0c1d2e-0000-4000-8000-000000000004'


def _action_field(plan, name: str, visible_for: str):
    return AttributeTypeFactory.create(
        object_content_type=ContentType.objects.get_for_model(Action),
        scope=plan,
        name=name,
        instances_visible_for=visible_for,
    )


@pytest.fixture
def report_type(plan_with_pages):
    public = _action_field(plan_with_pages, 'Progress', AttributeType.VisibleFor.PUBLIC)
    logged_in = _action_field(plan_with_pages, 'Internal comment', AttributeType.VisibleFor.AUTHENTICATED)
    report_type = ReportTypeFactory.create(plan=plan_with_pages)
    report_type.fields = json.dumps([
        {'type': 'attribute', 'value': {'attribute_type': public.pk}, 'id': PUBLIC_FIELD},
        {'type': 'attribute', 'value': {'attribute_type': logged_in.pk}, 'id': LOGGED_IN_FIELD},
        {'type': 'implementation_phase', 'value': {}, 'id': BUILT_IN_FIELD},
        # The public API has no values for tasks
        {'type': 'tasks', 'value': {}, 'id': TASKS_FIELD},
    ])
    report_type.save()
    return report_type


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


def _block_value(block: ReportComparisonBlock, report_type, reports, report_field=PUBLIC_FIELD):
    return block.to_python({
        'report_type': report_type.pk,
        'reports': [report.pk for report in reports],
        'report_field': report_field,
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


def test_compares_the_public_fields_of_the_template(report_type):
    assert comparable_fields(report_type) == [(PUBLIC_FIELD, 'Progress'), (BUILT_IN_FIELD, 'Implementation phase')]


@pytest.mark.parametrize('report_field', [LOGGED_IN_FIELD, TASKS_FIELD, 'not-a-field'])
def test_refuses_a_field_it_cannot_compare(report_type, report_field):
    block = ReportComparisonBlock()
    report = _report(report_type, '2025', 2025)

    with pytest.raises(StructBlockValidationError) as excinfo:
        block.clean(_block_value(block, report_type, [report], report_field=report_field))
    assert 'report_field' in excinfo.value.block_errors


def test_field_options_list_the_comparable_fields(client, plan_with_pages, plan_admin_user, report_type):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)

    response = client.get(f'/admin/plan_reports/report_type/report-fields/?report_type={report_type.pk}')
    assert response.json() == {
        'fields': [{'id': PUBLIC_FIELD, 'label': 'Progress'}, {'id': BUILT_IN_FIELD, 'label': 'Implementation phase'}]
    }


@pytest.mark.parametrize('query', ['other-plan', 'not-a-number', ''])
def test_field_options_only_cover_templates_of_plans_the_user_administers(client, plan_with_pages, plan_admin_user, query):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    if query == 'other-plan':
        query = str(ReportTypeFactory.create().pk)

    response = client.get(f'/admin/plan_reports/report_type/report-fields/?report_type={query}')
    assert response.status_code == 404


def test_field_select_keeps_the_value_in_a_hidden_input():
    html = ReportTypeFieldSelect().render('block-report_field', PUBLIC_FIELD, {'id': 'block-report_field'})
    assert f'<input type="hidden" name="block-report_field" value="{PUBLIC_FIELD}"' in html
    assert '<select id="block-report_field"' in html


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
    assert isinstance(draft, ActionListPage)
    assert draft.details_main_bottom is not None
    assert list(draft.details_main_bottom[0].value['reports']) == [report]


def test_migration_leaves_blocks_that_list_their_reports(action_list_page, report_type):
    block = {**_old_block(report_type.pk)}
    block['value'] = {**block['value'], 'reports': []}
    filler = _filler({report_type.pk: [1]})

    assert not filler.fill([block])
    assert block['value']['reports'] == []
