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
from people.tests.factories import PersonFactory
from people.wagtail_admin import PersonAdmin

if TYPE_CHECKING:
    from django.test.client import RequestFactory

    from actions.models import Plan
    from people.models import Person
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
