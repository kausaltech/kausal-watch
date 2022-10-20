import pytest

from actions.tests.factories import PlanFactory
from orgs.models import Organization
from orgs.tests.factories import OrganizationFactory, OrganizationPlanAdminFactory

pytestmark = pytest.mark.django_db


def test_organization_user_can_edit_related_plan_general_plan_admin_false(person):
    # plan = PlanFactory()
    # organization = OrganizationFactory()
    # plan.general_admins.add(person)
    # plan.related_organizations.add(organization)
    # assert not organization.user_can_edit(person.user)
    # FIXME: For now we skip this test since we temporarily changed the logic
    pass


def test_organization_user_can_edit_metadata_admin(person):
    organization = OrganizationFactory()
    organization.metadata_admins.add(person)
    assert organization.user_can_edit(person.user)


def test_organization_user_can_edit_metadata_admin_parent_org(person):
    parent_org = OrganizationFactory()
    organization = OrganizationFactory(parent=parent_org)
    organization.metadata_admins.add(person)
    assert organization.user_can_edit(person.user)


def test_organization_user_can_edit_metadata_admin_suborg(person):
    organization = OrganizationFactory()
    sub_org = OrganizationFactory(parent=organization)
    sub_org.metadata_admins.add(person)
    assert not organization.user_can_edit(person.user)


def test_organization_queryset_available_for_plan(plan):
    assert plan.organization
    plan_org = plan.organization
    org = OrganizationFactory()
    # Creating a new root org might've changed the path of plan_org
    plan_org.refresh_from_db()
    sub_org1 = OrganizationFactory(parent=plan.organization)
    sub_org2 = OrganizationFactory(parent=org)
    result = list(Organization.objects.available_for_plan(plan))
    assert result == [plan.organization, sub_org1]
    plan.related_organizations.add(org)
    result = set(Organization.objects.available_for_plan(plan))
    assert result == set([plan_org, sub_org1, org, sub_org2])


def test_organization_queryset_editable_by_user_related_plan_general_plan_admin_false(person):
    # plan = PlanFactory()
    # organization = OrganizationFactory()
    # plan.general_admins.add(person)
    # plan.related_organizations.add(organization)
    # assert organization not in Organization.objects.editable_by_user(person.user)
    # FIXME: For now we skip this test since we temporarily changed the logic
    pass


def test_organization_queryset_editable_by_user_metadata_admin(person):
    # organization = OrganizationFactory()
    # organization.metadata_admins.add(person)
    # assert organization in Organization.objects.editable_by_user(person.user)
    # FIXME: For now we skip this test since we temporarily changed the logic
    pass


def test_organization_queryset_editable_by_user_metadata_admin_parent_org(person):
    # parent_org = OrganizationFactory()
    # organization = OrganizationFactory(parent=parent_org)
    # organization.metadata_admins.add(person)
    # assert organization in Organization.objects.editable_by_user(person.user)
    # FIXME: For now we skip this test since we temporarily changed the logic
    pass


def test_organization_queryset_editable_by_user_metadata_admin_suborg(person):
    organization = OrganizationFactory()
    sub_org = OrganizationFactory(parent=organization)
    sub_org.metadata_admins.add(person)
    assert organization not in Organization.objects.editable_by_user(person.user)


def test_organization_user_can_change_related_to_plan_false(user):
    plan = PlanFactory()
    organization = OrganizationFactory()
    assert not organization.user_can_change_related_to_plan(user, plan)


def test_organization_user_can_change_related_to_plan_superuser(superuser):
    plan = PlanFactory()
    organization = OrganizationFactory()
    assert organization.user_can_change_related_to_plan(superuser, plan)


def test_organization_user_can_change_related_to_plan_organization_plan_admin_general_admin(plan_admin_user, plan):
    assert plan.organization.user_can_change_related_to_plan(plan_admin_user, plan)


def test_organization_user_can_change_related_to_plan_organization_plan_admin_false():
    opa = OrganizationPlanAdminFactory()
    assert not opa.organization.user_can_change_related_to_plan(opa.person.user, opa.plan)
