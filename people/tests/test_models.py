import pytest

from people.models import Person
from people.tests.factories import PersonFactory
from orgs.tests.factories import OrganizationFactory

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
