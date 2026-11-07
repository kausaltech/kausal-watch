"""
Tests for the columns of the person listing in the admin.

Rendering the whole index page needs a built staticfiles manifest, so the columns are exercised
directly against the queryset the listing uses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.urls import reverse
from wagtail.admin.ui.tables import TitleColumn

import pytest

from actions.models import PlanPublicSiteViewer
from actions.tests.factories import ActionFactory, PlanFactory
from actions.tests.utils import instantiate_view
from indicators.tests.factories import IndicatorContactFactory, IndicatorFactory
from orgs.tests.factories import OrganizationPlanAdminFactory
from people.models import Person
from people.tests.factories import PersonFactory
from people.wagtail_admin import PersonIndexView, PersonRoleFilterSet, PersonTable

if TYPE_CHECKING:
    from django.test.client import RequestFactory

    from actions.models import Plan
    from users.models import User

pytestmark = pytest.mark.django_db


def make_index_view(rf: RequestFactory, user: User, **params: str) -> PersonIndexView:
    request = rf.get('/', params)
    request.user = user
    view = instantiate_view(Person.snippet_viewset.index_view, PersonIndexView)  # type: ignore[attr-defined]
    view.setup(request)
    return view


def get_cell(rf: RequestFactory, user: User, person: Person, column: str, **params: str) -> Any:
    view = make_index_view(rf, user, **params)
    assert view.permission_policy is not None
    # The index view renders the listing with the active plan set on the permission policy
    with view.permission_policy.activate_plan_context(user.get_active_admin_plan()):  # type: ignore[attr-defined]
        listed = view.get_base_queryset().get(pk=person.pk)
        columns = {c.name: c for c in view.columns}
        return columns[column].get_value(listed)


def test_nameless_person_email_is_only_in_the_email_column(rf: RequestFactory, plan: Plan, plan_admin_user: User):
    person = PersonFactory.create(first_name='', last_name='', email='nameless@example.com', organization=plan.organization)
    assert 'nameless@example.com' not in get_cell(rf, plan_admin_user, person, 'first_name')
    assert 'nameless@example.com' in get_cell(rf, plan_admin_user, person, 'email')


class TestRoleColumn:
    def test_person_without_roles_has_no_badges(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        person = PersonFactory.create(organization=plan.organization)
        assert get_cell(rf, plan_admin_user, person, 'role') == ''

    def test_plan_admin(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        person = PersonFactory.create(organization=plan.organization, general_admin_plans=[plan])
        assert 'Plan admin' in get_cell(rf, plan_admin_user, person, 'role')

    def test_organization_admin(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        person = PersonFactory.create(organization=plan.organization)
        OrganizationPlanAdminFactory.create(plan=plan, person=person, organization=plan.organization)
        assert 'Organization admin' in get_cell(rf, plan_admin_user, person, 'role')

    def test_action_contact_person(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        action = ActionFactory.create(plan=plan)
        person = PersonFactory.create(organization=plan.organization, contact_for_actions=[action])
        assert 'Contact person' in get_cell(rf, plan_admin_user, person, 'role')

    def test_indicator_contact_person(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        indicator = IndicatorFactory.create(plans=[plan], organization=plan.organization)
        person = PersonFactory.create(organization=plan.organization)
        IndicatorContactFactory.create(indicator=indicator, person=person)
        assert 'Contact person' in get_cell(rf, plan_admin_user, person, 'role')

    def test_viewer(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        person = PersonFactory.create(organization=plan.organization)
        PlanPublicSiteViewer.objects.create(plan=plan, person=person)
        assert 'Viewer' in get_cell(rf, plan_admin_user, person, 'role')

    def test_several_roles_get_one_badge_each(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        action = ActionFactory.create(plan=plan)
        person = PersonFactory.create(organization=plan.organization, general_admin_plans=[plan], contact_for_actions=[action])
        cell = get_cell(rf, plan_admin_user, person, 'role')
        assert 'Plan admin' in cell
        assert 'Contact person' in cell
        assert 'Viewer' not in cell

    def test_roles_in_other_plans_are_not_shown(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        other_plan = PlanFactory.create()
        other_action = ActionFactory.create(plan=other_plan)
        person = PersonFactory.create(
            organization=plan.organization, general_admin_plans=[other_plan], contact_for_actions=[other_action]
        )
        OrganizationPlanAdminFactory.create(plan=other_plan, person=person, organization=plan.organization)
        PlanPublicSiteViewer.objects.create(plan=other_plan, person=person)
        assert get_cell(rf, plan_admin_user, person, 'role') == ''

    def test_shown_to_users_who_are_not_plan_admins(self, rf: RequestFactory, plan: Plan, action_contact_person_user: User):
        person = PersonFactory.create(organization=plan.organization, general_admin_plans=[plan])
        assert 'Plan admin' in get_cell(rf, action_contact_person_user, person, 'role')


def filter_by_role(rf: RequestFactory, user: User, value: str) -> set[Person]:
    view = make_index_view(rf, user, role=value)
    filterset = PersonRoleFilterSet({'role': value}, queryset=view.get_base_queryset(), request=view.request)
    return set(filterset.qs)


class TestRoleFilter:
    @pytest.fixture
    def people_by_role(self, plan: Plan, plan_admin_person: Person) -> dict[str, Person]:
        action = ActionFactory.create(plan=plan)
        org_admin = PersonFactory.create(organization=plan.organization)
        OrganizationPlanAdminFactory.create(plan=plan, person=org_admin, organization=plan.organization)
        viewer = PersonFactory.create(organization=plan.organization)
        PlanPublicSiteViewer.objects.create(plan=plan, person=viewer)
        return {
            'plan_admin': plan_admin_person,
            'organization_admin': org_admin,
            'contact_person': PersonFactory.create(organization=plan.organization, contact_for_actions=[action]),
            'viewer': viewer,
            'none': PersonFactory.create(organization=plan.organization),
        }

    def test_listing_is_filtered_by_role_only(self):
        assert list(PersonRoleFilterSet.base_filters) == ['role']

    def test_lookups_offer_every_role_and_no_role(self):
        assert [value for value, _label in PersonRoleFilterSet.base_filters['role'].extra['choices']] == [
            'plan_admin',
            'organization_admin',
            'contact_person',
            'viewer',
            'none',
        ]

    @pytest.mark.parametrize('role', ['plan_admin', 'organization_admin', 'contact_person', 'viewer', 'none'])
    def test_filter_by_role(self, rf: RequestFactory, plan_admin_user: User, people_by_role: dict[str, Person], role: str):
        assert filter_by_role(rf, plan_admin_user, role) == {people_by_role[role]}

    def test_filter_matches_people_holding_several_roles(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        action = ActionFactory.create(plan=plan)
        person = PersonFactory.create(organization=plan.organization, general_admin_plans=[plan], contact_for_actions=[action])
        assert person in filter_by_role(rf, plan_admin_user, 'plan_admin')
        assert person in filter_by_role(rf, plan_admin_user, 'contact_person')


class TestContactColumns:
    def get_columns(self, rf: RequestFactory, user: User, **params: str) -> list[str]:
        return get_column_names(rf, user, **params)

    def test_shown_when_filtering_by_contact_person(self, rf: RequestFactory, plan_admin_user: User):
        columns = self.get_columns(rf, plan_admin_user, role='contact_person')
        assert 'contact_for_actions' in columns
        assert 'contact_for_indicators' in columns

    @pytest.mark.parametrize('params', [{}, {'role': 'viewer'}])
    def test_hidden_otherwise(self, rf: RequestFactory, plan_admin_user: User, params: dict[str, str]):
        columns = self.get_columns(rf, plan_admin_user, **params)
        assert 'contact_for_actions' not in columns
        assert 'contact_for_indicators' not in columns

    def test_list_contacts_in_the_active_plan(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        action = ActionFactory.create(plan=plan, name='Plan action')
        other_action = ActionFactory.create(plan=PlanFactory.create(), name='Other action')
        person = PersonFactory.create(organization=plan.organization, contact_for_actions=[action, other_action])
        cell = get_cell(rf, plan_admin_user, person, 'contact_for_actions', role='contact_person')
        assert 'Plan action' in cell
        assert 'Other action' not in cell


class TestAvatar:
    @pytest.fixture
    def uploaded_avatar(self, monkeypatch: pytest.MonkeyPatch) -> str:
        url = '/media/avatar.png'
        monkeypatch.setattr(Person, 'get_avatar_url', lambda *_args, **_kwargs: url)
        return url

    def test_person_with_image(self, rf: RequestFactory, plan: Plan, plan_admin_user: User, uploaded_avatar: str):
        person = PersonFactory.create(organization=plan.organization)
        assert uploaded_avatar in get_cell(rf, plan_admin_user, person, 'avatar')

    def test_person_without_image_gets_placeholder(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        person = PersonFactory.create(organization=plan.organization)
        cell = get_cell(rf, plan_admin_user, person, 'avatar')
        assert 'people/avatar-placeholder.svg' in cell
        assert 'people/avatar-viewer-placeholder.svg' not in cell

    def test_viewer_without_image_gets_viewer_placeholder(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        person = PersonFactory.create(organization=plan.organization)
        PlanPublicSiteViewer.objects.create(plan=plan, person=person)
        assert 'people/avatar-viewer-placeholder.svg' in get_cell(rf, plan_admin_user, person, 'avatar')

    def test_viewer_with_image_gets_viewer_placeholder(
        self, rf: RequestFactory, plan: Plan, plan_admin_user: User, uploaded_avatar: str
    ):
        person = PersonFactory.create(organization=plan.organization)
        PlanPublicSiteViewer.objects.create(plan=plan, person=person)
        cell = get_cell(rf, plan_admin_user, person, 'avatar')
        assert 'people/avatar-viewer-placeholder.svg' in cell
        assert uploaded_avatar not in cell


def get_column_names(rf: RequestFactory, user: User, **params: str) -> list[str]:
    return [c.name for c in make_index_view(rf, user, **params).columns]


def get_column_header(rf: RequestFactory, user: User, column: str) -> str:
    columns = {c.name: c for c in make_index_view(rf, user).columns}
    return str(columns[column].label)


class TestEmailColumn:
    def test_follows_the_avatar_and_warning_icons(self, rf: RequestFactory, plan_admin_user: User):
        columns = get_column_names(rf, plan_admin_user)
        assert columns[:4] == ['avatar', 'cannot_access_admin_warning', 'email', 'first_name']

    def test_shown_to_users_who_are_not_plan_admins(self, rf: RequestFactory, action_contact_person_user: User):
        assert 'email' in get_column_names(rf, action_contact_person_user)

    def test_shows_the_email(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        person = PersonFactory.create(email='listed@example.com', organization=plan.organization)
        assert 'listed@example.com' in get_cell(rf, plan_admin_user, person, 'email')

    def test_links_to_the_edit_view(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        person = PersonFactory.create(email='listed@example.com', organization=plan.organization)
        edit_url = reverse('wagtailsnippets_people_person:edit', args=[person.pk])
        assert get_cell(rf, plan_admin_user, person, 'email') == f'<a href="{edit_url}">listed@example.com</a>'

    def test_is_plain_text_without_edit_rights(self, rf: RequestFactory, plan: Plan, action_contact_person_user: User):
        person = PersonFactory.create(email='listed@example.com', organization=plan.organization)
        assert get_cell(rf, action_contact_person_user, person, 'email') == 'listed@example.com'


class TestAttendedTrainingColumn:
    def test_replaces_participated_in_training(self, rf: RequestFactory, plan_admin_user: User):
        columns = get_column_names(rf, plan_admin_user)
        assert 'participated_in_training' not in columns
        assert 'attended_training' in columns

    def test_header_wraps(self, rf: RequestFactory, plan_admin_user: User):
        header = get_column_header(rf, plan_admin_user, 'attended_training')
        assert 'Attended training' in header
        assert 'person-listing-wrapped-header' in header

    def test_shows_whether_the_person_attended(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        attended = PersonFactory.create(organization=plan.organization, participated_in_training=True)
        not_attended = PersonFactory.create(organization=plan.organization, participated_in_training=False)
        assert get_cell(rf, plan_admin_user, attended, 'attended_training') is True
        assert get_cell(rf, plan_admin_user, not_attended, 'attended_training') is False


class TestActionsMenu:
    def test_rows_have_no_hover_buttons(self, rf: RequestFactory, plan_admin_user: User):
        assert not any(isinstance(c, TitleColumn) for c in make_index_view(rf, plan_admin_user).columns)

    def test_is_the_last_column(self, rf: RequestFactory, plan_admin_user: User):
        assert get_column_names(rf, plan_admin_user)[-1] == 'actions'
        assert get_column_names(rf, plan_admin_user, role='contact_person')[-1] == 'actions'

    def test_lists_the_actions_in_a_dropdown(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        person = PersonFactory.create(organization=plan.organization)
        cell = get_cell(rf, plan_admin_user, person, 'actions')
        assert 'data-controller="w-dropdown"' in cell
        assert 'icon-dots-horizontal' in cell
        assert f'/{person.pk}/' in cell
        assert 'Edit' in cell
        assert 'Deactivate' in cell

    def test_superuser_can_view_as_the_user(self, rf: RequestFactory, plan: Plan, superuser: User):
        action = ActionFactory.create(plan=plan)
        person = PersonFactory.create(organization=plan.organization, contact_for_actions=[action])
        superuser.selected_admin_plan = plan
        superuser.save()
        assert 'View as user' in get_cell(rf, superuser, person, 'actions')


class TestNoAdminAccessWarning:
    def enable_access_requests(self, plan: Plan) -> None:
        plan.features.enable_access_requests = True
        plan.features.save()

    def make_viewer(self, plan: Plan) -> Person:
        person = PersonFactory.create(organization=plan.organization)
        PlanPublicSiteViewer.objects.create(plan=plan, person=person)
        return person

    def test_hidden_for_viewers_when_access_requests_are_enabled(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        self.enable_access_requests(plan)
        person = self.make_viewer(plan)
        assert get_cell(rf, plan_admin_user, person, 'cannot_access_admin_warning') == ''

    def test_shown_for_viewers_when_access_requests_are_disabled(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        person = self.make_viewer(plan)
        assert 'icon-warning' in get_cell(rf, plan_admin_user, person, 'cannot_access_admin_warning')

    def test_shown_for_other_people_without_access(self, rf: RequestFactory, plan: Plan, plan_admin_user: User):
        self.enable_access_requests(plan)
        person = PersonFactory.create(organization=plan.organization)
        assert 'icon-warning' in get_cell(rf, plan_admin_user, person, 'cannot_access_admin_warning')

    @pytest.mark.parametrize(('access_requests', 'highlighted'), [(True, False), (False, True)])
    def test_viewer_row_highlight(
        self, rf: RequestFactory, plan: Plan, plan_admin_user: User, access_requests: bool, highlighted: bool
    ):
        if access_requests:
            self.enable_access_requests(plan)
        person = self.make_viewer(plan)
        view = make_index_view(rf, plan_admin_user)
        listed = view.get_base_queryset().get(pk=person.pk)
        table = view.get_table([listed])
        assert isinstance(table, PersonTable)
        assert ('warning-row' in table.get_row_attrs(listed).get('class', '')) is highlighted
