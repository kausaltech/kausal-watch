"""
Tests for the columns of the person listing in the admin.

Rendering the whole index page needs a built staticfiles manifest, so the list display callables
are exercised directly against the queryset the listing uses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from actions.models import PlanPublicSiteViewer
from actions.tests.factories import ActionFactory, PlanFactory
from indicators.tests.factories import IndicatorContactFactory, IndicatorFactory
from orgs.tests.factories import OrganizationPlanAdminFactory
from people.models import Person
from people.tests.factories import PersonFactory
from people.wagtail_admin import PersonAdmin, PersonRoleFilter

if TYPE_CHECKING:
    from django.http import HttpRequest
    from django.test.client import RequestFactory

    from actions.models import Plan
    from users.models import User

pytestmark = pytest.mark.django_db


def get_cell(rf: RequestFactory, user: User, person: Person, column: str, **params: str) -> Any:
    request = rf.get('/', params)
    request.user = user
    person_admin = PersonAdmin()
    listed = person_admin.get_queryset(request).get(pk=person.pk)
    fields = {getattr(f, '__name__', f): f for f in person_admin.get_list_display(request)}
    return fields[column](listed)


def test_person_without_name_is_listed_by_email(rf: RequestFactory, plan: Plan, plan_admin_user: User):
    person = PersonFactory.create(first_name='', last_name='', email='nameless@example.com', organization=plan.organization)
    assert 'nameless@example.com' in get_cell(rf, plan_admin_user, person, 'first_name')


def test_person_with_name_is_not_listed_by_email(rf: RequestFactory, plan: Plan, plan_admin_user: User):
    person = PersonFactory.create(first_name='Named', last_name='', email='named@example.com', organization=plan.organization)
    cell = get_cell(rf, plan_admin_user, person, 'first_name')
    assert 'Named' in cell
    assert 'named@example.com' not in cell


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


def make_role_filter(request: HttpRequest, person_admin: PersonAdmin, params: dict[str, list[str]]) -> PersonRoleFilter:
    # The wagtail_modeladmin index view passes its own ModelAdmin where Django's stubs expect Django's
    return PersonRoleFilter(request, params, Person, person_admin)  # type: ignore[arg-type]


def filter_by_role(rf: RequestFactory, user: User, value: str) -> set[Person]:
    request = rf.get('/', {'role': value})
    request.user = user
    person_admin = PersonAdmin()
    role_filter = make_role_filter(request, person_admin, {'role': [value]})
    return set(role_filter.queryset(request, person_admin.get_queryset(request)))


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
        assert PersonAdmin.list_filter == (PersonRoleFilter,)

    def test_lookups_offer_every_role_and_no_role(self, rf: RequestFactory, plan_admin_user: User):
        request = rf.get('/')
        request.user = plan_admin_user
        role_filter = make_role_filter(request, PersonAdmin(), {})
        assert [value for value, _label in role_filter.lookup_choices] == [
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
        request = rf.get('/', params)
        request.user = user
        return [getattr(f, '__name__', f) for f in PersonAdmin().get_list_display(request)]

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
