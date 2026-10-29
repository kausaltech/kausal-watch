"""Report templates live in the Reports menu, and each template's report listing leads back to the template."""

from __future__ import annotations

from wagtail.admin.menu import settings_menu

import pytest

from aplans.cache import PlanSpecificCache

from actions.tests.factories import PlanFactory
from admin_site.permissions import PlanRelatedPermissionPolicy
from admin_site.tests.factories import ClientPlanFactory
from admin_site.wagtail_hooks import report_menu
from reports.models import ReportType
from reports.tests.factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db

REPORT_TYPES_PATH = '/admin/plan_reports/report_type/'
REPORTS_PATH = '/admin/plan_reports/report/'


def _menu_request(rf, user, plan):
    request = rf.get('/admin/')
    request.user = user
    request.admin_cache = PlanSpecificCache(plan=plan)
    request.get_active_admin_plan = lambda: plan
    return request


def _labels(menu, request) -> list[str]:
    return [str(item.label) for item in menu.menu_items_for_request(request)]


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


def test_reports_menu_lists_the_templates_after_their_reports(rf, plan, plan_admin_user):
    report_type = ReportTypeFactory.create(plan=plan, name='Annual report')
    request = _menu_request(rf, plan_admin_user, plan)
    assert _labels(report_menu, request) == [report_type.name, 'Report templates']
    # The same icon as the Reports menu itself
    assert report_menu.menu_items_for_request(request)[0].icon_name == 'doc-full'


def test_report_templates_are_not_in_the_settings_menu(rf, plan, plan_admin_user):
    request = _menu_request(rf, plan_admin_user, plan)
    labels = _labels(settings_menu, request)
    assert 'Report templates' not in labels
    assert 'Report types' not in labels


def test_reports_menu_offers_templates_before_any_exist(rf, plan, plan_admin_user):
    """Without the item, a plan with no report templates would have no way to create its first one."""
    request = _menu_request(rf, plan_admin_user, plan)
    assert _labels(report_menu, request) == ['Report templates']


def test_report_templates_item_is_set_apart_only_below_templates(rf, plan, plan_admin_user):
    request = _menu_request(rf, plan_admin_user, plan)
    [templates_item] = report_menu.menu_items_for_request(request)
    assert templates_item.icon_name == 'cog'
    assert 'sidebar-menu-item__link--separated' not in templates_item.classname

    ReportTypeFactory.create(plan=plan)
    templates_item = report_menu.menu_items_for_request(request)[-1]
    assert 'sidebar-menu-item__link--separated' in templates_item.classname


def test_reports_menu_is_empty_for_contact_person(rf, plan, action_contact_person_user):
    ReportTypeFactory.create(plan=plan)
    request = _menu_request(rf, action_contact_person_user, plan)
    assert _labels(report_menu, request) == []


def test_report_listing_is_titled_by_its_template_and_links_to_it(admin_client, plan_with_pages):
    report_type = ReportTypeFactory.create(plan=plan_with_pages, name='Quarterly council report')
    response = admin_client.get(REPORTS_PATH, {'report_type': report_type.pk})
    assert response.status_code == 200
    content = response.content.decode()
    assert f'<title>{report_type.name}' in content
    assert f'href="/admin/plan_reports/report_type/edit/{report_type.pk}/"' in content


def test_report_listing_of_another_plans_template_offers_own_templates(admin_client):
    other_report_type = ReportTypeFactory.create(plan=PlanFactory.create(), name='Other plan template')
    response = admin_client.get(REPORTS_PATH, {'report_type': other_report_type.pk})
    assert response.status_code == 302
    assert response['Location'] == REPORT_TYPES_PATH


def test_report_listing_has_no_template_filter_to_clear(admin_client, plan_with_pages):
    """The template is what the page is about, not a filter: clearing it would leave the page showing other reports."""
    report_type = ReportTypeFactory.create(plan=plan_with_pages)
    content = admin_client.get(REPORTS_PATH, {'report_type': report_type.pk}).content.decode()
    assert 'name="report_type"' not in content


def test_refreshed_report_listing_keeps_its_template(admin_client, plan_with_pages):
    """Searching, sorting and paging refresh only the results, which must stay the template's reports."""
    report_type = ReportTypeFactory.create(plan=plan_with_pages)
    report = ReportFactory.create(type=report_type, name='Report of this template')
    other_report = ReportFactory.create(type=ReportTypeFactory.create(plan=plan_with_pages), name='Report of another')
    response = admin_client.get(f'{REPORTS_PATH}results/', {'report_type': report_type.pk})
    content = response.content.decode()
    assert report.name in content
    assert other_report.name not in content


def test_report_listing_breadcrumbs_lead_to_the_templates(admin_client, plan_with_pages):
    report_type = ReportTypeFactory.create(plan=plan_with_pages)
    content = admin_client.get(REPORTS_PATH, {'report_type': report_type.pk}).content.decode()
    assert f'href="{REPORT_TYPES_PATH}"' in content


@pytest.mark.parametrize('view', ['add', 'edit'])
def test_report_form_breadcrumbs_lead_to_its_template(admin_client, plan_with_pages, view):
    report_type = ReportTypeFactory.create(plan=plan_with_pages)
    report = ReportFactory.create(type=report_type)
    path = f'{REPORTS_PATH}add/' if view == 'add' else f'{REPORTS_PATH}edit/{report.pk}/'
    content = admin_client.get(path, {'report_type': report_type.pk}).content.decode()
    assert f'href="{REPORT_TYPES_PATH}"' in content
    assert f'href="{REPORTS_PATH}?report_type={report_type.pk}"' in content


def test_saved_report_returns_to_its_template_without_the_query_parameter(admin_client, plan_with_pages):
    """A report opened from elsewhere, such as the action's reporting tab, still returns to its template's reports."""
    report = ReportFactory.create(type=ReportTypeFactory.create(plan=plan_with_pages))
    response = admin_client.post(
        f'{REPORTS_PATH}edit/{report.pk}/',
        {'name': 'Renamed', 'start_date': report.start_date.isoformat(), 'end_date': report.end_date.isoformat()},
    )
    assert response.status_code == 302
    assert response['Location'] == f'{REPORTS_PATH}?report_type={report.type.pk}'


def test_deleted_report_returns_to_its_template(admin_client, plan_with_pages):
    report = ReportFactory.create(type=ReportTypeFactory.create(plan=plan_with_pages))
    delete_path = f'{REPORTS_PATH}delete/{report.pk}/'
    assert admin_client.get(delete_path).status_code == 200
    response = admin_client.post(delete_path)
    assert response.status_code == 302
    assert response['Location'] == f'{REPORTS_PATH}?report_type={report.type.pk}'


def test_report_form_without_template_keeps_wagtails_breadcrumbs(admin_client, plan_with_pages):
    """The add button always names a template, but a hand-typed URL without one must not break the page."""
    ReportTypeFactory.create(plan=plan_with_pages)
    response = admin_client.get(f'{REPORTS_PATH}add/')
    assert response.status_code == 200
    assert f'href="{REPORT_TYPES_PATH}"' not in response.content.decode()


def test_report_listing_offers_no_edit_template_without_permission_to_change_it(admin_client, plan_with_pages, monkeypatch):
    """Plan admins may change every template of their plan, so take the permission away just for this check."""
    report_type = ReportTypeFactory.create(plan=plan_with_pages)
    original = PlanRelatedPermissionPolicy.user_has_permission_for_instance

    def deny_changing_templates(self, user, action, instance):
        if isinstance(instance, ReportType) and action == 'change':
            return False
        return original(self, user, action, instance)

    monkeypatch.setattr(PlanRelatedPermissionPolicy, 'user_has_permission_for_instance', deny_changing_templates)
    content = admin_client.get(REPORTS_PATH, {'report_type': report_type.pk}).content.decode()
    assert report_type.name in content
    assert f'{REPORT_TYPES_PATH}edit/{report_type.pk}/' not in content
