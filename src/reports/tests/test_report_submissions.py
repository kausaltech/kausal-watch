"""Admins follow and manage the actions' submissions to a report from the report listing and the report itself."""

from __future__ import annotations

import datetime

from django.utils.formats import date_format

import pytest

from actions.tests.factories import ActionContactFactory, ActionFactory
from admin_site.tests.factories import ClientPlanFactory
from reports.models import ActionSnapshot
from reports.tests.factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db

REPORTS_PATH = '/admin/plan_reports/report/'
UNDO_PATH = '/admin/actions/action/undo_marking_action_as_complete/{action}/{report}/'


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def report(plan_with_pages):
    report_type = ReportTypeFactory.create(plan=plan_with_pages, name='Quarterly report')
    return ReportFactory.create(
        type=report_type,
        name='Q3 2026',
        start_date=datetime.date(2026, 7, 1),
        end_date=datetime.date(2026, 9, 30),
    )


@pytest.fixture
def submitted_action(action, report, plan_admin_user):
    action.mark_as_complete_for_report(report, plan_admin_user)
    return action


@pytest.fixture
def unsubmitted_action(plan_with_pages):
    return ActionFactory.create(plan=plan_with_pages, name='Not yet submitted')


def _edit_page(admin_client, report) -> str:
    return admin_client.get(f'{REPORTS_PATH}edit/{report.pk}/').content.decode()


def test_report_listing_shows_dates_status_and_submissions(admin_client, report, submitted_action, unsubmitted_action):
    content = admin_client.get(REPORTS_PATH, {'report_type': report.type.pk}).content.decode()
    assert f'{date_format(report.start_date)} – {date_format(report.end_date)}' in content  # noqa: RUF001
    assert 'Open' in content
    assert '1 / 2' in content


def test_report_listing_shows_completed_reports_as_complete(admin_client, plan_admin_user, report, submitted_action):
    report.mark_as_complete(plan_admin_user)
    content = admin_client.get(REPORTS_PATH, {'report_type': report.type.pk}).content.decode()
    assert 'Complete' in content


def test_report_lists_its_submissions(admin_client, plan_admin_user, report, submitted_action, unsubmitted_action):
    ActionContactFactory.create(action=unsubmitted_action, primary_contact=True)
    content = _edit_page(admin_client, report)
    assert '2 actions' in content
    assert '1 submitted' in content
    assert '1 not submitted' in content
    assert submitted_action.name in content
    assert unsubmitted_action.name in content
    assert f'by {plan_admin_user.get_full_name() or plan_admin_user.email}' in content
    assert str(unsubmitted_action.contact_persons.get().person) in content


def test_report_offers_undoing_a_submission_and_returns_to_itself(admin_client, report, submitted_action):
    undo_path = UNDO_PATH.format(action=submitted_action.pk, report=report.pk)
    edit_path = f'{REPORTS_PATH}edit/{report.pk}/'
    assert f'href="{undo_path}?next=' in _edit_page(admin_client, report)

    confirmation = admin_client.get(undo_path, {'next': edit_path}).content.decode()
    assert f'href="{edit_path}" class="button button-secondary"' in confirmation

    response = admin_client.post(f'{undo_path}?next={edit_path}', {'next': edit_path})
    assert response.status_code == 302
    assert response['Location'] == edit_path
    assert not ActionSnapshot.objects.filter(report=report).exists()


def test_undo_ignores_a_return_address_on_another_site(admin_client, report, submitted_action):
    undo_path = UNDO_PATH.format(action=submitted_action.pk, report=report.pk)
    response = admin_client.post(undo_path, {'next': 'https://example.com/'})
    assert response.status_code == 302
    assert response['Location'] == '/admin/actions/action/'


def test_completed_report_offers_no_undo(admin_client, plan_admin_user, report, submitted_action):
    report.mark_as_complete(plan_admin_user)
    assert 'undo_marking_action_as_complete' not in _edit_page(admin_client, report)


def test_new_report_has_no_submissions_to_list(admin_client, report):
    content = admin_client.get(f'{REPORTS_PATH}add/', {'report_type': report.type.pk}).content.decode()
    assert 'report-submissions' not in content
    assert 'Action submissions' not in content
