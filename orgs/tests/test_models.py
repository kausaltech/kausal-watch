import pytest

from actions.tests.factories import PlanFactory
from orgs.tests.factories import OrganizationFactory
from users.tests.factories import OrganizationAdminFactory

pytestmark = pytest.mark.django_db


def test_organization_user_can_edit_related_plan_admin(user):
    plan = PlanFactory()
    organization = OrganizationFactory()
    plan.general_admins.add(user)
    plan.related_organizations.add(organization)
    assert organization.user_can_edit(user)


def test_organization_user_can_edit_related_plan_admin_parent_org_related(user):
    plan = PlanFactory()
    parent_org = OrganizationFactory()
    organization = OrganizationFactory(parent=parent_org)
    plan.general_admins.add(user)
    plan.related_organizations.add(organization)
    assert organization.user_can_edit(user)


def test_organization_user_can_edit_related_plan_admin_suborg_related(user):
    plan = PlanFactory()
    organization = OrganizationFactory()
    sub_org = OrganizationFactory(parent=organization)
    plan.general_admins.add(user)
    plan.related_organizations.add(sub_org)
    assert not organization.user_can_edit(user)


def test_organization_user_can_edit_false(user):
    organization = OrganizationFactory()
    assert not organization.user_can_edit(user)


def test_organization_user_can_edit_organization_admin(user):
    organization = OrganizationFactory()
    OrganizationAdminFactory(user=user, organization=organization)
    assert organization.user_can_edit(user)
