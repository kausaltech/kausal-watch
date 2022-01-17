import pytest

from actions.tests.factories import ActionContactFactory, ActionResponsiblePartyFactory
from indicators.tests.factories import IndicatorContactFactory
from people.tests.factories import PersonFactory
from orgs.tests.factories import OrganizationFactory, OrganizationAdminFactory

pytestmark = pytest.mark.django_db


def test_is_contact_person_for_action():
    contact = ActionContactFactory()
    user = contact.person.user
    action = contact.action
    assert user.is_contact_person_for_action()
    assert user.is_contact_person_for_action(action)


def test_is_contact_person_for_action_false(user, action):
    assert not user.is_contact_person_for_action()
    assert not user.is_contact_person_for_action(action)


def test_is_contact_person_for_indicator():
    contact = IndicatorContactFactory()
    user = contact.person.user
    indicator = contact.indicator
    assert user.is_contact_person_for_indicator()
    assert user.is_contact_person_for_indicator(indicator)


def test_is_contact_person_for_indicator_false(user, indicator):
    assert not user.is_contact_person_for_indicator()
    assert not user.is_contact_person_for_indicator(indicator)


def test_is_general_admin_for_plan_superuser(superuser, plan):
    assert superuser.is_general_admin_for_plan()
    assert superuser.is_general_admin_for_plan(plan)


def test_is_general_admin_for_plan_false(user, plan):
    assert not user.is_general_admin_for_plan()
    assert not user.is_general_admin_for_plan(plan)


def test_is_general_admin_for_plan(user, plan):
    user.general_admin_plans.add(plan)
    assert user.is_general_admin_for_plan()
    assert user.is_general_admin_for_plan(plan)


def test_is_organization_admin_for_action_false(user, action):
    assert not user.is_organization_admin_for_action()
    assert not user.is_organization_admin_for_action(action)


def test_is_organization_admin_for_action(action):
    org = action.plan.organization
    person = PersonFactory(organization=org)
    plan = action.plan
    OrganizationAdminFactory(organization=org, person=person, plan=plan)
    ActionResponsiblePartyFactory(action=action, organization=org)
    user = person.user
    # User's organization is responsible party for action
    assert user.is_organization_admin_for_action()
    assert user.is_organization_admin_for_action(action)


def test_is_organization_admin_for_action_not_responsible(action):
    org = action.plan.organization
    person = PersonFactory(organization=org)
    plan = action.plan
    OrganizationAdminFactory(organization=org, person=person, plan=plan)
    user = person.user
    # User is organization admin, but the user's organization is not a responsible party for the action
    assert not user.is_organization_admin_for_action()
    assert not user.is_organization_admin_for_action(action)


def test_is_organization_admin_for_action_not_admin(action):
    org = action.plan.organization
    ActionResponsiblePartyFactory(action=action, organization=org)
    person = PersonFactory(organization=org)
    user = person.user
    # User's organization is responsible party but user is not organization admin
    assert not user.is_organization_admin_for_action()
    assert not user.is_organization_admin_for_action(action)


def test_get_adminable_organizations_superuser(superuser):
    organization = OrganizationFactory()
    assert list(superuser.get_adminable_organizations()) == [organization]


def test_get_adminable_organizations_is_not_admin(user):
    OrganizationFactory()
    assert list(user.get_adminable_organizations()) == []


def test_get_adminable_organizations_descendants(superuser):
    organization = OrganizationFactory()
    sub_org = OrganizationFactory(parent=organization)
    assert list(superuser.get_adminable_organizations()) == [organization, sub_org]


def test_get_adminable_organizations_organization_admin():
    org_admin = OrganizationAdminFactory()
    assert list(org_admin.person.user.get_adminable_organizations()) == [org_admin.organization]