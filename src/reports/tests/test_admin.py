from __future__ import annotations

from unittest.mock import Mock

import pytest

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
