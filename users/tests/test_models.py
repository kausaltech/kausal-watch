import pytest

from actions.tests.factories import ActionContactFactory, ActionResponsiblePartyFactory
from indicators.tests.factories import IndicatorContactFactory
from people.tests.factories import PersonFactory
from orgs.tests.factories import OrganizationFactory, OrganizationPlanAdminFactory

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


def test_is_general_admin_for_plan(plan_admin_user, plan):
    assert plan_admin_user.is_general_admin_for_plan()
    assert plan_admin_user.is_general_admin_for_plan(plan)


def test_is_organization_admin_for_action_false(user, action):
    assert not user.is_organization_admin_for_action()
    assert not user.is_organization_admin_for_action(action)


def test_is_organization_admin_for_action(action):
    org = action.plan.organization
    person = PersonFactory(organization=org)
    plan = action.plan
    OrganizationPlanAdminFactory(organization=org, person=person, plan=plan)
    ActionResponsiblePartyFactory(action=action, organization=org)
    user = person.user
    # User's organization is responsible party for action
    assert user.is_organization_admin_for_action()
    assert user.is_organization_admin_for_action(action)


def test_is_organization_admin_for_action_not_responsible(action):
    org = action.plan.organization
    person = PersonFactory(organization=org)
    plan = action.plan
    OrganizationPlanAdminFactory(organization=org, person=person, plan=plan)
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
    assert organization in superuser.get_adminable_organizations().all()


def test_get_adminable_organizations_is_not_admin(user):
    organization = OrganizationFactory()
    assert organization not in user.get_adminable_organizations()


def test_get_adminable_organizations_descendants(superuser):
    organization = OrganizationFactory()
    sub_org = OrganizationFactory(parent=organization)
    adminable = superuser.get_adminable_organizations()
    assert organization in adminable
    assert sub_org in adminable


def test_get_adminable_organizations_organization_plan_admin():
    org_admin = OrganizationPlanAdminFactory()
    assert list(org_admin.person.user.get_adminable_organizations()) == [org_admin.organization]
