from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.http import Http404

import pytest

from aplans.utils import RestrictedVisibilityModel

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


class ExportViewRequestMixin:
    def _get(self, rf, plan_identifier, user=None, authorization=None, **params):
        from reports.views import export_report_view

        headers = {'Authorization': authorization} if authorization is not None else {}
        request = rf.get(f'/report_export/{plan_identifier}/', params, headers=headers)
        request.user = user if user is not None else AnonymousUser()
        return export_report_view(request, plan_identifier=plan_identifier)


@pytest.mark.django_db
class TestExportReportView(ExportViewRequestMixin):
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

    def test_unpublished_plan_hidden_from_anonymous_user_raises_404(self, rf):
        plan = PlanFactory.create(published_at=None, visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)
        with pytest.raises(Http404):
            self._get(rf, plan.identifier)

    def test_inactive_plan_raises_404(self, rf, user_factory):
        plan = PlanFactory.create(is_active=False)
        with pytest.raises(Http404):
            self._get(rf, plan.identifier, user=user_factory(is_superuser=True))

    def test_unpublished_plan_is_exported_for_user_who_may_view_it(self, rf, mock_export, user_factory):
        plan = PlanFactory.create(published_at=None, visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)
        response = self._get(rf, plan.identifier, user=user_factory(is_superuser=True))
        assert response.status_code == 200

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
        assert mock_export.call_args.kwargs['all_fields'] is False

    def test_invalid_fields_returns_400(self, rf, plan, superuser):
        response = self._get(rf, plan.identifier, user=superuser, fields='some')
        assert response.status_code == 400

    def test_all_fields_forbidden_for_anonymous_user(self, rf, plan, mock_export):
        with pytest.raises(PermissionDenied):
            self._get(rf, plan.identifier, fields='all')

    def test_all_fields_forbidden_for_user_without_plan_access(self, rf, plan, mock_export, user_factory):
        with pytest.raises(PermissionDenied):
            self._get(rf, plan.identifier, user=user_factory(), fields='all')

    def test_all_fields_allowed_for_public_site_viewer(self, rf, plan, mock_export, user_factory, person_factory):
        user = user_factory()
        plan.public_site_viewers.create(person=person_factory(user=user))
        response = self._get(rf, plan.identifier, user=user, fields='all')
        assert response.status_code == 200
        assert mock_export.call_args.kwargs['all_fields'] is True

    def test_all_fields_allowed_for_plan_admin(self, rf, plan, mock_export, plan_admin_user):
        response = self._get(rf, plan.identifier, user=plan_admin_user, fields='all')
        assert response.status_code == 200
        assert mock_export.call_args.kwargs['all_fields'] is True

    def test_missing_action_list_page_raises_404(self, rf, plan):
        from reports.models import ActionListPageNotFoundError

        with (
            patch(
                'reports.views.export_dashboard_report_for_plan',
                side_effect=ActionListPageNotFoundError(plan),
            ),
            pytest.raises(Http404),
        ):
            self._get(rf, plan.identifier)


def token_auth_as(user=None, error=None):
    from kausal_common.auth.tokens import TokenAuthError, TokenAuthResult

    if error is not None:
        result = TokenAuthResult(error=TokenAuthError(id=error, description='Token rejected'))
    else:
        result = TokenAuthResult(user=user)
    return patch('reports.views.authenticate_from_authorization_header', return_value=result)


def public_site_viewer(plan, user_factory, person_factory):
    user = user_factory()
    plan.public_site_viewers.create(person=person_factory(user=user))
    return user


@pytest.mark.django_db
class TestExportReportViewTokenAuth(ExportViewRequestMixin):
    """The public UI's export route authenticates with the ID token it holds, not with a session cookie."""

    def test_token_user_gets_all_fields(self, rf, plan, mock_export, user_factory, person_factory):
        viewer = public_site_viewer(plan, user_factory, person_factory)
        with token_auth_as(viewer):
            response = self._get(rf, plan.identifier, authorization='Bearer token', fields='all')
        assert response.status_code == 200
        assert mock_export.call_args[0][2] == viewer
        assert mock_export.call_args.kwargs['all_fields'] is True

    def test_token_user_takes_precedence_over_session_user(self, rf, plan, mock_export, superuser, user_factory):
        with token_auth_as(user_factory()), pytest.raises(PermissionDenied):
            self._get(rf, plan.identifier, user=superuser, authorization='Bearer token', fields='all')

    def test_invalid_token_returns_401(self, rf, plan, mock_export, superuser):
        with token_auth_as(error='invalid_token'):
            response = self._get(rf, plan.identifier, user=superuser, authorization='Bearer token')
        assert response.status_code == 401
        mock_export.assert_not_called()

    def test_token_of_inactive_user_returns_401(self, rf, plan, mock_export, user_factory, person_factory):
        viewer = public_site_viewer(plan, user_factory, person_factory)
        viewer.is_active = False
        viewer.save()
        with token_auth_as(viewer):
            response = self._get(rf, plan.identifier, authorization='Bearer token', fields='all')
        assert response.status_code == 401
        mock_export.assert_not_called()

    def test_internal_plan_is_exported_for_token_user(self, rf, mock_export, user_factory, person_factory):
        plan = PlanFactory.create(published_at=None, visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)
        viewer = public_site_viewer(plan, user_factory, person_factory)
        with token_auth_as(viewer):
            response = self._get(rf, plan.identifier, authorization='Bearer token')
        assert response.status_code == 200

    def test_real_access_token_authenticates(self, rf, plan, mock_export, user_factory, person_factory):
        from django.apps import apps

        if not apps.is_installed('oauth2_provider'):
            pytest.skip('requires the OAuth2 provider')
        from kausal_common.tests.test_token_auth import create_access_token

        viewer = public_site_viewer(plan, user_factory, person_factory)
        token = create_access_token(viewer, resource=[])
        response = self._get(rf, plan.identifier, authorization=f'Bearer {token}', fields='all')
        assert response.status_code == 200
        assert mock_export.call_args[0][2] == viewer


@pytest.mark.django_db
class TestGenerateForPlanDashboard:
    def _action_list_page(self, plan):
        from pages.models import ActionListPage

        return plan.root_page.get_children().type(ActionListPage).get().specific

    def test_finds_nested_action_list_page(self, plan_with_pages):
        """The ActionListPage may live deeper than a direct child of the root page (see WATCH-BACKEND-4YN)."""
        from reports.models import ReportType

        plan = plan_with_pages
        action_list_page = self._action_list_page(plan)
        # Nest the ActionListPage under a sibling so it is no longer a direct child of the root page.
        sibling = plan.root_page.get_children().exclude(pk=action_list_page.pk).first()
        action_list_page.move(sibling, pos='last-child')

        # Previously raised Page.DoesNotExist because the lookup only considered direct children.
        report_type = ReportType.generate_for_plan_dashboard(plan, AnonymousUser())
        assert report_type is not None

    def test_missing_action_list_page_raises(self, plan_with_pages):
        from reports.models import ActionListPageNotFoundError, ReportType

        plan = plan_with_pages
        self._action_list_page(plan).delete()

        report_type = ReportType(plan=plan, name='Dashboard export', fields=None)
        with pytest.raises(ActionListPageNotFoundError):
            report_type.get_action_list_page()


@pytest.mark.django_db
class TestExportVisibilityForUser:
    """The export must contain the actions of a plan the user is allowed to see, published or not."""

    def _unpublished_plan(self, plan_with_pages):
        plan = plan_with_pages
        plan.published_at = None
        plan.visibility = RestrictedVisibilityModel.VisibilityState.INTERNAL
        plan.save()
        return plan

    def test_unpublished_plan_export_contains_actions_for_permitted_user(self, plan_with_pages, user_factory):
        from actions.tests.factories import ActionFactory
        from reports.export import export_dashboard_report_for_plan

        plan = self._unpublished_plan(plan_with_pages)
        action = ActionFactory.create(plan=plan)
        user = user_factory(is_superuser=True)

        output, _filename = export_dashboard_report_for_plan(plan, 'csv', user)
        assert action.name in output
