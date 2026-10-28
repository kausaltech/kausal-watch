"""The report form groups its fields and shows which template the report is made from."""

from __future__ import annotations

import pytest

from admin_site.tests.factories import ClientPlanFactory
from reports.tests.factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db

REPORTS_PATH = '/admin/plan_reports/report/'


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def report_type(plan_with_pages):
    # The export skips a field configured twice, and so does the form
    return ReportTypeFactory.create(
        plan=plan_with_pages,
        name='Quarterly report',
        fields__0='implementation_phase',
        fields__1='implementation_phase',
    )


def _template_fields(content: str) -> str:
    start = content.index('class="report-template-fields"')
    return content[start : content.index('</ul>', start)]


def test_report_form_shows_its_template_and_fields(admin_client, report_type):
    report = ReportFactory.create(type=report_type)
    content = admin_client.get(f'{REPORTS_PATH}edit/{report.pk}/').content.decode()
    assert 'Quarterly report' in content
    assert '1 field configured on this template:' in content
    assert _template_fields(content).count('Implementation phase') == 1


def test_new_report_form_shows_the_template_it_is_made_from(admin_client, report_type):
    content = admin_client.get(f'{REPORTS_PATH}add/', {'report_type': report_type.pk}).content.decode()
    assert 'report-template-fields' in content
    assert 'Implementation phase' in _template_fields(content)


def test_report_form_says_when_its_template_has_no_fields(admin_client, plan_with_pages):
    report = ReportFactory.create(type=ReportTypeFactory.create(plan=plan_with_pages, fields=[]))
    content = admin_client.get(f'{REPORTS_PATH}edit/{report.pk}/').content.decode()
    assert 'No fields are configured on this template.' in content


def test_report_form_groups_details_and_visibility(admin_client, report_type):
    report = ReportFactory.create(type=report_type)
    content = admin_client.get(f'{REPORTS_PATH}edit/{report.pk}/').content.decode()
    assert 'Report details' in content
    assert 'The period during which action data for this report is collected.' in content
    assert 'Visibility' in content
    assert 'Show in action reporting tab' in content


def test_report_form_has_no_public_setting(admin_client, report_type):
    """The report comparison blocks choose the reports they show themselves (plan 3, Phase C)."""
    report = ReportFactory.create(type=report_type)
    content = admin_client.get(f'{REPORTS_PATH}edit/{report.pk}/').content.decode()
    assert 'name="is_public"' not in content
