"""An action's reporting tab compares its values in the latest reports of each template, and submits it to open ones."""

from __future__ import annotations

import datetime

import pytest

from actions.tests.factories import ActionImplementationPhaseFactory
from admin_site.tests.factories import ClientPlanFactory
from reports.action_reporting import REPORTS_PER_TEMPLATE, get_action_report_tables
from reports.tests.factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def report_type(plan_with_pages):
    return ReportTypeFactory.create(plan=plan_with_pages, name='Quarterly report', fields__0='implementation_phase')


@pytest.fixture
def phases(plan_with_pages):
    return [ActionImplementationPhaseFactory.create(plan=plan_with_pages, name=name) for name in ('Planning', 'Done')]


@pytest.fixture
def action(action, phases):
    action.implementation_phase = phases[0]
    action.save()
    return action


def _report(report_type, name, start, **kwargs):
    kwargs.setdefault('show_in_reporting_tab', True)
    return ReportFactory.create(
        type=report_type, name=name, start_date=start, end_date=start + datetime.timedelta(days=89), **kwargs
    )


def test_tab_shows_the_latest_reports_of_each_template(plan_admin_user, action, report_type):
    reports = [_report(report_type, f'Q{i}', datetime.date(2026, 1, 1) + datetime.timedelta(days=91 * i)) for i in range(4)]
    _report(report_type, 'Hidden', datetime.date(2030, 1, 1), show_in_reporting_tab=False)

    [table] = get_action_report_tables(action, plan_admin_user)
    assert table.report_type == report_type
    assert [column.report for column in table.columns] == list(reversed(reports))[:REPORTS_PER_TEMPLATE]


def test_unsubmitted_action_shows_its_current_values_and_can_be_submitted(plan_admin_user, action, report_type):
    report = _report(report_type, 'Q3 2026', datetime.date(2026, 7, 1))
    [table] = get_action_report_tables(action, plan_admin_user)
    [column] = table.columns
    assert table.rows == [('Implementation phase', ['Planning'])]
    assert column.submitted_at is None
    assert column.submit_url == (
        f'/admin/actions/action/mark_action_as_complete/{action.pk}/{report.pk}/'
        f'?next=%2Fadmin%2Factions%2Faction%2Fedit%2F{action.pk}%2F%23tab-reporting'
    )
    assert column.resubmit_url is None


def test_submitted_action_shows_its_submitted_values_and_can_be_resubmitted(plan_admin_user, action, report_type, phases):
    report = _report(report_type, 'Q3 2026', datetime.date(2026, 7, 1))
    action.mark_as_complete_for_report(report, plan_admin_user)
    action.implementation_phase = phases[1]
    action.save()

    [table] = get_action_report_tables(action, plan_admin_user)
    [column] = table.columns
    assert table.rows == [('Implementation phase', ['Planning'])]
    assert column.submitted_at is not None
    assert column.submit_url is None
    assert column.resubmit_url is not None
    assert column.resubmit_url.startswith(f'/admin/actions/action/resubmit_action_for_report/{action.pk}/{report.pk}/')


def test_completed_report_offers_no_submission(plan_admin_user, action, report_type):
    report = _report(report_type, 'Q3 2026', datetime.date(2026, 7, 1))
    report.mark_as_complete(plan_admin_user)
    [table] = get_action_report_tables(action, plan_admin_user)
    [column] = table.columns
    assert column.is_captured
    # Completing the report captured the action; nobody submitted it
    assert column.submitted_at is None
    assert column.submit_url is None
    assert column.resubmit_url is None


def test_editor_without_permission_to_submit_sees_values_only(action_contact_person_user, action, report_type):
    report_type.only_plan_admins_can_mark_actions_as_complete = True
    report_type.save()
    _report(report_type, 'Q3 2026', datetime.date(2026, 7, 1))
    [table] = get_action_report_tables(action, action_contact_person_user)
    [column] = table.columns
    assert table.rows == [('Implementation phase', ['Planning'])]
    assert column.submit_url is None


def test_reporting_tab_renders_the_reports(client, plan_with_pages, plan_admin_user, action, report_type):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    _report(report_type, 'Q3 2026', datetime.date(2026, 7, 1))
    content = client.get(f'/admin/actions/action/edit/{action.pk}/').content.decode()
    assert 'class="listing action-reports"' in content
    assert 'Q3 2026' in content
    assert 'Submit action for report' in content
    # The reports come after the fields that are filled in
    assert content.index('name="internal_notes"') < content.index('class="listing action-reports"')


def test_submitting_from_the_reporting_tab_returns_to_it(client, plan_with_pages, plan_admin_user, action, report_type):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    report = _report(report_type, 'Q3 2026', datetime.date(2026, 7, 1))
    [table] = get_action_report_tables(action, plan_admin_user)
    submit_url = table.columns[0].submit_url
    assert submit_url is not None

    return_url = f'/admin/actions/action/edit/{action.pk}/#tab-reporting'
    response = client.post(submit_url, {'next': return_url})
    assert response.status_code == 302
    assert response['Location'] == return_url
    assert action.is_complete_for_report(report)
