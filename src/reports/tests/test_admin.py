from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest

if TYPE_CHECKING:
    from pages.models import ActionListPage
    from reports.models import ReportType

pytestmark = pytest.mark.django_db


class TestReportAdminButtonHelper:
    """Tests for ReportAdminButtonHelper preserving report_type parameter."""

    @pytest.fixture
    def report_type(self, plan):
        """Create a report type for testing."""
        from reports.tests.factories import ReportTypeFactory

        return ReportTypeFactory.create(plan=plan, name='Test Report Type')

    def test_add_button_shown_with_report_type_parameter(self, rf, plan, plan_admin_user, report_type):
        """Add button should be shown when report_type parameter is present."""
        from reports.wagtail_admin import ReportAdmin, ReportAdminButtonHelper

        admin = ReportAdmin()
        request = rf.get(f'/admin/?report_type={report_type.id}')
        request.user = plan_admin_user

        view = Mock()
        view.model = admin.model
        view.url_helper = Mock()
        view.url_helper.create_url = '/admin/create/'
        view.permission_helper = Mock()

        helper = ReportAdminButtonHelper(view, request)
        result = helper.add_button()

        assert result is not None
        assert f'report_type={report_type.id}' in result['url']

    def test_add_button_hidden_without_report_type_parameter(self, rf, plan, plan_admin_user):
        """Add button should be hidden when report_type parameter is missing."""
        from reports.wagtail_admin import ReportAdmin, ReportAdminButtonHelper

        admin = ReportAdmin()
        request = rf.get('/admin/')
        request.user = plan_admin_user

        view = Mock()
        view.model = admin.model
        view.url_helper = Mock()
        view.permission_helper = Mock()

        helper = ReportAdminButtonHelper(view, request)
        result = helper.add_button()

        assert result is None

    def test_delete_button_preserves_report_type_parameter(self, rf, plan, plan_admin_user, report_type):
        """Delete button should preserve report_type parameter in URL."""
        from reports.wagtail_admin import ReportAdminButtonHelper

        request = rf.get(f'/admin/?report_type={report_type.id}')
        request.user = plan_admin_user

        view = Mock()
        view.model = Mock()
        view.model._meta = Mock()
        view.model._meta.verbose_name = 'report'
        view.url_helper = Mock()
        view.url_helper.get_action_url = Mock(side_effect=lambda action, pk: f'/admin/{action}/{pk}/')
        view.permission_helper = Mock()

        helper = ReportAdminButtonHelper(view, request)
        result = helper.delete_button(pk=1)

        assert result is not None
        assert f'report_type={report_type.id}' in result['url']

    def test_edit_button_preserves_report_type_parameter(self, rf, plan, plan_admin_user, report_type):
        """Edit button should preserve report_type parameter in URL."""
        from reports.wagtail_admin import ReportAdminButtonHelper

        request = rf.get(f'/admin/?report_type={report_type.id}')
        request.user = plan_admin_user

        view = Mock()
        view.model = Mock()
        view.model._meta = Mock()
        view.model._meta.verbose_name = 'report'
        view.url_helper = Mock()
        view.url_helper.get_action_url = Mock(side_effect=lambda action, pk: f'/admin/{action}/{pk}/')
        view.permission_helper = Mock()

        helper = ReportAdminButtonHelper(view, request)
        result = helper.edit_button(pk=1)

        assert result is not None
        assert f'report_type={report_type.id}' in result['url']


class TestReportTypeDeleteView:
    """Deleting a report type must not break the action details pages that compare its reports."""

    @pytest.fixture
    def report_type(self, plan_with_pages):
        from reports.tests.factories import ReportTypeFactory

        return ReportTypeFactory.create(plan=plan_with_pages)

    @pytest.fixture
    def action_list_page(self, plan_with_pages):
        page = plan_with_pages.get_action_list_page()
        assert page is not None
        return page

    @pytest.fixture
    def admin_client(self, client, plan_with_pages, plan_admin_user):
        from admin_site.tests.factories import ClientPlanFactory

        ClientPlanFactory.create(plan=plan_with_pages)
        client.force_login(plan_admin_user)
        return client

    @staticmethod
    def _delete_url(report_type: ReportType) -> str:
        from django.urls import reverse

        from reports.wagtail_admin import ReportTypeAdmin

        return reverse(ReportTypeAdmin().url_helper.get_action_url_name('delete'), kwargs={'instance_pk': report_type.pk})

    @staticmethod
    def _add_comparison_block(page: ActionListPage, report_type: ReportType) -> None:
        page.details_main_bottom = [('report_comparison', {'report_type': report_type, 'report_field': 'some-uuid'})]

    def test_used_report_type_cannot_be_deleted(self, admin_client, action_list_page, report_type):
        from reports.models import ReportType

        self._add_comparison_block(action_list_page, report_type)
        action_list_page.save()

        response = admin_client.get(self._delete_url(report_type))
        assert response.status_code == 200
        assert response.context['usage'].pages == [action_list_page]
        assert b'Yes, delete' not in response.content

        response = admin_client.post(self._delete_url(report_type))
        assert response.status_code == 200
        assert ReportType.objects.filter(pk=report_type.pk).exists()

    def test_report_type_used_only_in_draft_cannot_be_deleted(self, admin_client, action_list_page, report_type):
        from reports.models import ReportType

        self._add_comparison_block(action_list_page, report_type)
        action_list_page.save_revision()

        response = admin_client.get(self._delete_url(report_type))
        usage = response.context['usage']
        assert usage.pages == []
        assert usage.draft_pages == [action_list_page]

        admin_client.post(self._delete_url(report_type))
        assert ReportType.objects.filter(pk=report_type.pk).exists()

    def test_other_report_type_in_block_does_not_block_deletion(self, admin_client, action_list_page, report_type):
        from reports.models import ReportType
        from reports.tests.factories import ReportTypeFactory

        other = ReportTypeFactory.create(plan=report_type.plan)
        self._add_comparison_block(action_list_page, other)
        action_list_page.save()

        response = admin_client.post(self._delete_url(report_type))
        assert response.status_code == 302
        assert not ReportType.objects.filter(pk=report_type.pk).exists()

    def test_unused_report_type_warns_about_deleted_reports(self, admin_client, action, plan_admin_user, report_type):
        from reports.models import ReportType
        from reports.tests.factories import ReportFactory

        report = ReportFactory.create(type=report_type)
        report.mark_as_complete(plan_admin_user)
        assert report.action_snapshots.exists()

        response = admin_client.get(self._delete_url(report_type))
        usage = response.context['usage']
        assert not usage.blocks_deletion
        assert usage.report_count == 1
        assert usage.snapshot_count == report.action_snapshots.count()
        assert b'permanently deletes' in response.content

        response = admin_client.post(self._delete_url(report_type))
        assert response.status_code == 302
        assert not ReportType.objects.filter(pk=report_type.pk).exists()


def test_report_comparison_block_without_report_type_compares_nothing():
    from reports.blocks.report_comparison_block import ReportComparisonBlock

    assert ReportComparisonBlock().reports_to_compare(None, {'report_type': None}) == []
