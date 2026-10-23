"""The report and report type admin views only show and change the active plan's objects."""

from __future__ import annotations

import json
import re

import pytest

from actions.tests.factories import PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from reports.models import Report, ReportType
from reports.tests.factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db

REPORT_TYPES_PATH = '/admin/plan_reports/report_type/'
REPORTS_PATH = '/admin/plan_reports/report/'


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def own_report_type(plan_with_pages):
    return ReportTypeFactory.create(plan=plan_with_pages, name='Own report type')


@pytest.fixture
def other_plan_report_type():
    return ReportTypeFactory.create(plan=PlanFactory.create(), name='Other plan report type')


@pytest.fixture
def own_report(own_report_type):
    return ReportFactory.create(type=own_report_type, name='Own report')


@pytest.fixture
def other_plan_report(other_plan_report_type):
    return ReportFactory.create(type=other_plan_report_type, name='Other plan report')


def _add_report_path(response_content: bytes, report_type: ReportType) -> str:
    match = re.search(rf'href="({REPORTS_PATH}[a-z]+/\?report_type={report_type.pk})"', response_content.decode())
    assert match is not None
    return match.group(1)


def _menu_links(response_content: bytes) -> list[tuple[str, str]]:
    match = re.search(r'<script id="wagtail-sidebar-props" type="application/json">(.*?)</script>', response_content.decode())
    assert match is not None
    links: list[tuple[str, str]] = []

    def collect(node):
        if isinstance(node, dict):
            if node.get('_type') == 'wagtail.sidebar.LinkMenuItem':
                links.append((node['_args'][0]['label'], node['_args'][0]['url']))
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)

    collect(json.loads(match.group(1)))
    return links


def test_admin_menu_links_each_report_type(admin_client, own_report_type, other_plan_report_type):
    links = _menu_links(admin_client.get('/admin/account/').content)
    assert (own_report_type.name, f'{REPORTS_PATH}?report_type={own_report_type.pk}') in links
    assert not any(label == other_plan_report_type.name for label, _url in links)


def test_admin_menu_links_report_types(admin_client):
    links = _menu_links(admin_client.get('/admin/account/').content)
    assert ('Report types', REPORT_TYPES_PATH) in links


def test_contact_person_menu_has_no_report_links(client, action_contact_person_user, own_report_type):
    client.force_login(action_contact_person_user)
    links = _menu_links(client.get('/admin/account/').content)
    assert links
    assert not any(url.startswith('/admin/plan_reports/') for _label, url in links)


def test_report_type_listing_shows_only_active_plan(admin_client, own_report_type, other_plan_report_type):
    response = admin_client.get(REPORT_TYPES_PATH)
    assert response.status_code == 200
    assert own_report_type.name in response.content.decode()
    assert other_plan_report_type.name not in response.content.decode()


def test_report_listing_filters_by_report_type(admin_client, own_report_type, own_report, other_plan_report):
    other_type = ReportTypeFactory.create(plan=own_report_type.plan)
    report_of_other_type = ReportFactory.create(type=other_type, name='Report of another type')

    response = admin_client.get(REPORTS_PATH, {'report_type': own_report_type.pk})
    assert response.status_code == 200
    content = response.content.decode()
    assert own_report.name in content
    assert report_of_other_type.name not in content
    assert other_plan_report.name not in content


def test_report_listing_hides_other_plans_reports(admin_client, other_plan_report):
    response = admin_client.get(REPORTS_PATH, {'report_type': other_plan_report.type.pk})
    assert other_plan_report.name not in response.content.decode()


def test_report_listing_offers_add_for_its_report_type(admin_client, own_report_type):
    response = admin_client.get(REPORTS_PATH, {'report_type': own_report_type.pk})
    _add_report_path(response.content, own_report_type)


def test_report_listing_without_report_type_offers_no_add(admin_client, own_report):
    response = admin_client.get(REPORTS_PATH)
    assert own_report.name in response.content.decode()
    assert re.search(rf'href="{REPORTS_PATH}(create|add)/', response.content.decode()) is None


def test_report_listing_offers_report_actions(admin_client, own_report_type, own_report):
    response = admin_client.get(REPORTS_PATH, {'report_type': own_report_type.pk})
    content = response.content.decode()
    assert f'{REPORTS_PATH}download/{own_report.pk}/' in content
    assert f'{REPORTS_PATH}mark_report_as_complete/{own_report.pk}/' in content
    assert f'{REPORTS_PATH}edit/{own_report.pk}/?report_type={own_report_type.pk}' in content
    assert f'{REPORTS_PATH}delete/{own_report.pk}/?report_type={own_report_type.pk}' in content


def test_marking_report_complete_returns_to_the_listing(admin_client, own_report):
    response = admin_client.post(f'{REPORTS_PATH}mark_report_as_complete/{own_report.pk}/')
    assert response.status_code == 302
    assert response['Location'] == REPORTS_PATH
    own_report.refresh_from_db()
    assert own_report.is_complete


def test_undoing_report_completion(admin_client, own_report, plan_admin_user):
    own_report.mark_as_complete(plan_admin_user)

    response = admin_client.post(f'{REPORTS_PATH}undo_marking_report_as_complete/{own_report.pk}/')
    assert response.status_code == 302
    own_report.refresh_from_db()
    assert not own_report.is_complete


def test_created_report_gets_type_from_query(admin_client, own_report_type):
    response = admin_client.get(REPORTS_PATH, {'report_type': own_report_type.pk})
    add_path = _add_report_path(response.content, own_report_type)

    response = admin_client.post(
        add_path,
        {'name': 'New report', 'start_date': '2026-01-01', 'end_date': '2026-12-31', 'is_public': 'on'},
    )
    assert response.status_code == 302
    report = Report.objects.get(name='New report')
    assert report.type == own_report_type


def test_created_report_type_belongs_to_active_plan(admin_client, plan_with_pages):
    response = admin_client.get(REPORT_TYPES_PATH)
    match = re.search(rf'href="({REPORT_TYPES_PATH}[a-z]+/)"', response.content.decode())
    assert match is not None

    response = admin_client.post(match.group(1), {'name': 'New report type', 'fields-count': '0'})
    assert response.status_code == 302
    assert ReportType.objects.get(name='New report type').plan == plan_with_pages


def test_admin_can_edit_report_of_own_plan(admin_client, own_report):
    response = admin_client.post(
        f'{REPORTS_PATH}edit/{own_report.pk}/',
        {
            'name': 'Renamed report',
            'start_date': own_report.start_date.isoformat(),
            'end_date': own_report.end_date.isoformat(),
        },
    )
    assert response.status_code == 302
    own_report.refresh_from_db()
    assert own_report.name == 'Renamed report'


def test_report_of_other_plan_offers_plan_switch(admin_client, other_plan_report):
    response = admin_client.get(f'{REPORTS_PATH}edit/{other_plan_report.pk}/')
    assert response.status_code == 302
    assert response['Location'].startswith(f'/admin/change-admin-plan/{other_plan_report.type.plan.pk}/')


def test_admin_cannot_delete_report_of_other_plan(admin_client, other_plan_report):
    admin_client.post(f'{REPORTS_PATH}delete/{other_plan_report.pk}/')
    assert Report.objects.filter(pk=other_plan_report.pk).exists()


def test_admin_cannot_delete_report_type_of_other_plan(admin_client, other_plan_report_type):
    admin_client.post(f'{REPORT_TYPES_PATH}delete/{other_plan_report_type.pk}/')
    assert ReportType.objects.filter(pk=other_plan_report_type.pk).exists()


@pytest.mark.parametrize('path', [REPORTS_PATH, REPORT_TYPES_PATH])
def test_listings_offer_no_bulk_actions(admin_client, own_report, path):
    response = admin_client.get(path, {'report_type': own_report.type.pk} if path == REPORTS_PATH else {})
    assert own_report.type.name in response.content.decode()
    assert 'bulk-action-checkbox' not in response.content.decode()


def test_bulk_delete_is_not_available(admin_client, own_report):
    report_type = own_report.type
    admin_client.post(f'/admin/bulk/reports/report/delete/?id={own_report.pk}')
    admin_client.post(f'/admin/bulk/reports/reporttype/delete/?id={report_type.pk}')
    assert Report.objects.filter(pk=own_report.pk).exists()
    assert ReportType.objects.filter(pk=report_type.pk).exists()


@pytest.mark.parametrize('path', [REPORTS_PATH, REPORT_TYPES_PATH])
def test_contact_person_cannot_list(client, action_contact_person_user, own_report, path):
    client.force_login(action_contact_person_user)
    response = client.get(path, {'report_type': own_report.type.pk})
    assert response.status_code != 200
    assert own_report.name not in response.content.decode()
