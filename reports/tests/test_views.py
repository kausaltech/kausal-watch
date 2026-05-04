from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.http import Http404

import pytest

from actions.tests.factories import PlanFactory


def test_mark_action_as_complete_view_accepts_as_view_kwargs():
    """
    as_view() must accept all kwargs that are passed when the view is used.

    Django's View.as_view() checks hasattr(cls, key) for each kwarg.
    Type annotations without default values do NOT create class attributes,
    so they will cause TypeError if passed as kwargs to as_view().

    This test ensures that MarkActionAsCompleteView has action_pk and report_pk
    as class attributes (with default values) so they can be passed to as_view().
    """
    from reports.views import MarkActionAsCompleteView

    # Verify the class attributes exist
    assert hasattr(MarkActionAsCompleteView, 'action_pk'), 'MarkActionAsCompleteView must have action_pk as a class attribute'
    assert hasattr(MarkActionAsCompleteView, 'report_pk'), 'MarkActionAsCompleteView must have report_pk as a class attribute'
    assert hasattr(MarkActionAsCompleteView, 'complete'), 'MarkActionAsCompleteView must have complete as a class attribute'

    # Verify as_view() accepts the kwargs (these are passed in actions/action_admin.py)
    try:
        MarkActionAsCompleteView.as_view(
            model_admin=None,
            action_pk='1',
            report_pk='1',
            complete=True,
        )
    except TypeError as e:
        if 'invalid keyword' in str(e):
            pytest.fail(f'as_view() rejected a keyword argument: {e}')
        raise


def test_mark_report_as_complete_view_accepts_as_view_kwargs():
    """
    as_view() must accept all kwargs that are passed when the view is used.

    This test ensures that MarkReportAsCompleteView has report_pk and complete
    as class attributes (with default values) so they can be passed to as_view().
    """
    from reports.views import MarkReportAsCompleteView

    # Verify the class attributes exist
    assert hasattr(MarkReportAsCompleteView, 'report_pk'), 'MarkReportAsCompleteView must have report_pk as a class attribute'
    assert hasattr(MarkReportAsCompleteView, 'complete'), 'MarkReportAsCompleteView must have complete as a class attribute'

    # Verify as_view() accepts the kwargs (these are passed in reports/wagtail_admin.py)
    try:
        MarkReportAsCompleteView.as_view(
            model_admin=None,
            report_pk='1',
            complete=True,
        )
    except TypeError as e:
        if 'invalid keyword' in str(e):
            pytest.fail(f'as_view() rejected a keyword argument: {e}')
        raise


@pytest.fixture
def mock_export():
    with patch('reports.views.export_dashboard_report_for_plan', return_value=(b'data', 'report.xlsx')) as m:
        yield m


@pytest.mark.django_db
class TestExportReportView:
    def _get(self, rf, plan_identifier, **params):
        from reports.views import export_report_view

        request = rf.get(f'/report_export/{plan_identifier}/', params)
        request.user = AnonymousUser()
        return export_report_view(request, plan_identifier=plan_identifier)

    @pytest.mark.parametrize('format', ['pdf', 'json', 'xml'])
    def test_invalid_format_returns_400(self, rf, plan, format):
        response = self._get(rf, plan.identifier, format=format)
        assert response.status_code == 400

    @pytest.mark.parametrize(
        'actions',
        [
            "1,2'",  # trailing quote
            '1,foo,3',  # non-integer token
            'abc',  # entirely non-numeric
        ],
    )
    def test_invalid_actions_returns_400(self, rf, plan, actions):
        response = self._get(rf, plan.identifier, actions=actions)
        assert response.status_code == 400

    def test_nonexistent_plan_raises_404(self, rf):
        with pytest.raises(Http404):
            self._get(rf, 'does-not-exist')

    def test_non_live_plan_raises_404(self, rf):
        plan = PlanFactory.create(published_at=None)
        with pytest.raises(Http404):
            self._get(rf, plan.identifier)

    @pytest.mark.parametrize(
        ('format', 'expected_content_type'),
        [
            ('xlsx', 'spreadsheetml'),
            ('csv', 'text/csv'),
            (None, 'spreadsheetml'),  # default format is xlsx
        ],
    )
    def test_valid_format_returns_200_with_correct_content_type(self, rf, plan, mock_export, format, expected_content_type):
        params = {'format': format} if format is not None else {}
        response = self._get(rf, plan.identifier, **params)
        assert response.status_code == 200
        assert expected_content_type in response['Content-Type']

    def test_valid_actions_filter_passes_ids_to_exporter(self, rf, plan, mock_export):
        response = self._get(rf, plan.identifier, actions='1,2,3')
        assert response.status_code == 200
        assert mock_export.call_args[0][3] == [1, 2, 3]

    def test_no_actions_param_passes_none_to_exporter(self, rf, plan, mock_export):
        response = self._get(rf, plan.identifier)
        assert response.status_code == 200
        assert mock_export.call_args[0][3] is None
