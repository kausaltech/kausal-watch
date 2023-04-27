import datetime

import pytest

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.utils import timezone

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


def test_non_superuser_cannot_delete_person_or_deactivate_user(plan):
    User = get_user_model()
    normal_user = UserFactory()
    person = PersonFactory()

    assert person.user is not None
    assert person.user.pk is not None
    assert person.user.is_active
    initial_person_count = Person.objects.count()
    initial_user_count = User.objects.count()

    with pytest.raises(PermissionDenied):
        person.delete_and_deactivate_corresponding_user(normal_user)

    assert Person.objects.count() == initial_person_count
    assert User.objects.count() == initial_user_count
    assert person.user.is_active
    assert person.user.deactivated_by is None
    assert person.user.deactivated_at is None


def test_superuser_can_delete_person_or_deactivate_user(plan):
    User = get_user_model()
    superuser = UserFactory(is_superuser=True)
    person = PersonFactory()
    target_user = person.user

    assert person.user is not None and person.user.pk is not None
    initial_person_count = Person.objects.count()
    initial_user_count = User.objects.count()

    person.delete_and_deactivate_corresponding_user(superuser)

    assert Person.objects.count() == initial_person_count - 1
    assert User.objects.count() == initial_user_count
    assert target_user.is_active is False
    assert target_user.deactivated_by == superuser
    assert timezone.now() - target_user.deactivated_at < datetime.timedelta(milliseconds=1000)
