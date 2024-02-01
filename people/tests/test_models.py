import pytest
from datetime import datetime
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


def test_person_change_email_changes_user_email():
    email = 'foo@example.com'
    person = PersonFactory(email=email)
    user = person.user
    assert person.email == email
    assert user.email == email
    email = 'bar@example.com'
    person.email = email
    person.save()
    user.refresh_from_db()
    # User should stay the same, but only the email address should change
    assert person.user == user
    assert person.email == email
    assert user.email == email


def test_person_delete_and_deactivate_corresponding_user(plan_admin_user):
    person = PersonFactory()
    user = person.user
    person.delete_and_deactivate_corresponding_user(plan_admin_user)
    assert not Person.objects.filter(pk=person.pk).exists()
    user.refresh_from_db()
    assert not user.is_active
    assert user.deactivated_by == plan_admin_user


def test_person_reactivate_deactivated_user(plan_admin_user):
    now = datetime(2000, 1, 1, 0, 0)
    user = UserFactory(is_active=False, deactivated_by=plan_admin_user, deactivated_at=now)
    person = PersonFactory(email=user.email)
    assert person.user == user
    user.refresh_from_db()
    assert user.is_active


def test_person_reactivate_user_resets_password(plan_admin_user):
    now = datetime(2000, 1, 1, 0, 0)
    user = UserFactory(is_active=False, deactivated_by=plan_admin_user, deactivated_at=now)
    password = 'foo'
    user.set_password(password)
    user.save()
    assert user.check_password(password)
    PersonFactory(email=user.email)
    user.refresh_from_db()
    assert not user.check_password(password)


def test_person_change_email_resets_password():
    old_email = 'old@example.com'
    new_email = 'new@example.com'
    password = 'foo'
    person = PersonFactory(email=old_email)
    user = person.user
    user.set_password(password)
    user.save()
    assert user.check_password(password)
    person.email = new_email
    person.save()
    user.refresh_from_db()
    assert not user.check_password(password)


def test_person_change_email_to_deactivated_users_email(plan_admin_user):
    now = datetime(2000, 1, 1, 0, 0)
    old_email = 'old@example.com'
    new_email = 'new@example.com'
    old_user = UserFactory(email=old_email, is_active=False, deactivated_by=plan_admin_user, deactivated_at=now)
    person = PersonFactory(email=new_email)
    new_user = person.user
    assert new_user != old_user
    assert new_user.is_active
    person.email = old_email
    person.save()
    assert person.user == old_user
    old_user.refresh_from_db()
    assert old_user.is_active
    new_user.refresh_from_db()
    assert not new_user.is_active
