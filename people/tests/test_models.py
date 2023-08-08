import pytest

from people.models import Person
from people.tests.factories import PersonFactory
from orgs.tests.factories import OrganizationFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_person_query_set_available_for_plan_unrelated(plan):
    person = PersonFactory()
    # person.organization is different from plan.organization
    assert person not in Person.objects.available_for_plan(plan)


def test_person_query_set_available_for_plan_plan_organization(plan, person):
    # person.organization is the same as plan.organization
    assert person in Person.objects.available_for_plan(plan)


def test_person_query_set_available_for_plan_plan_organization_descendant(plan):
    org = OrganizationFactory(parent=plan.organization)
    person = PersonFactory(organization=org)
    assert person in Person.objects.available_for_plan(plan)


def test_person_query_set_available_for_plan_related_organization(plan):
    org = OrganizationFactory()
    plan.related_organizations.add(org)
    person = PersonFactory(organization=org)
    assert person in Person.objects.available_for_plan(plan)


def test_person_query_set_available_for_plan_related_organization_descendant(plan):
    org = OrganizationFactory()
    plan.related_organizations.add(org)
    sub_org = OrganizationFactory(parent=org)
    person = PersonFactory(organization=sub_org)
    assert person in Person.objects.available_for_plan(plan)


def test_non_superuser_cannot_get_permissions_to_delete_person_or_deactivate_user(plan):
    normal_user = UserFactory()
    person = PersonFactory()

    assert person.user is not None
    assert person.user.pk is not None
    assert person.user.is_active
    assert not normal_user.can_edit_or_delete_person_within_plan(person, plan=plan)


def test_superuser_can_get_permissions_to_delete_person_or_deactivate_user(plan):
    superuser = UserFactory(is_superuser=True)
    person = PersonFactory()

    assert person.user is not None and person.user.pk is not None
    assert superuser.can_edit_or_delete_person_within_plan(person, plan=plan)


def test_plan_admin_can_get_permissions_to_delete_person_or_deactivate_user(plan, plan_admin_user):
    person = PersonFactory()
    assert plan_admin_user.is_general_admin_for_plan(plan)
    assert person.user is not None and person.user.pk is not None
    plan.organization = person.organization
    plan.save()
    assert plan_admin_user.can_edit_or_delete_person_within_plan(person, plan=plan)
