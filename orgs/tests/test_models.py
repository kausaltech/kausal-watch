import pytest

from actions.tests.factories import PlanFactory
from orgs.models import Organization
from orgs.tests.factories import OrganizationFactory, OrganizationPlanAdminFactory

pytestmark = pytest.mark.django_db


def test_organization_user_can_edit_related_plan_general_plan_admin_false(user):
    plan = PlanFactory()
    organization = OrganizationFactory()
    plan.general_admins.add(user)
    plan.related_organizations.add(organization)
    assert not organization.user_can_edit(user)


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


def test_organization_queryset_editable_by_user_related_plan_general_plan_admin_false(person):
    plan = PlanFactory()
    organization = OrganizationFactory()
    plan.general_admins.add(person.user)
    plan.related_organizations.add(organization)
    assert organization not in Organization.objects.editable_by_user(person.user)


def test_organization_queryset_editable_by_user_metadata_admin(person):
    organization = OrganizationFactory()
    organization.metadata_admins.add(person)
    assert organization in Organization.objects.editable_by_user(person.user)


def test_organization_queryset_editable_by_user_metadata_admin_parent_org(person):
    parent_org = OrganizationFactory()
    organization = OrganizationFactory(parent=parent_org)
    organization.metadata_admins.add(person)
    assert organization in Organization.objects.editable_by_user(person.user)


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


def test_organization_user_can_change_related_to_plan_organization_plan_admin():
    opa = OrganizationPlanAdminFactory()
    assert opa.organization.user_can_change_related_to_plan(opa.person.user, opa.plan)
