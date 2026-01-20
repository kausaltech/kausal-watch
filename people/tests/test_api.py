from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

import pytest

from actions.api import PersonSerializer
from actions.tests.utils import assert_log_entry_created, count_log_entries
from audit_logging.models import PlanScopedModelLogEntry
from people.models import Person

pytestmark = pytest.mark.django_db


@pytest.fixture
def person_list_url():
    return reverse('person-list')


def test_person_post_creates_log_entry(
        api_client, plan, person_list_url, plan_admin_person, organization_factory):
    """Test that creating a person creates a PlanScopedModelLogEntry with action='wagtail.create'."""
    # Create organization and link it to the plan for the new person we're creating

    api_client.force_login(plan_admin_person.user)

    response = api_client.post(person_list_url + f'?plan={plan.identifier}', data=[{
        'first_name': 'Test',
        'last_name': 'Person',
        'email': 'test.person@example.com',
        'organization': plan.organization.pk,
    }])
    assert response.status_code == 201

    created_person = Person.objects.get(email='test.person@example.com')
    assert_log_entry_created(created_person, 'wagtail.create', plan_admin_person.user, plan)


def test_person_put_creates_log_entry(
        api_client, plan, person_list_url, plan_admin_person, person_factory):
    """Test that updating a person creates a PlanScopedModelLogEntry with action='wagtail.edit'."""
    api_client.force_login(plan_admin_person.user)

    person = person_factory(first_name='Original', last_name='Name', organization=plan.organization)

    response = api_client.put(person_list_url + f'?plan={plan.identifier}', data=[{
        'id': person.id,
        'first_name': 'Updated',
        'last_name': 'Name',
        'email': person.email,
        'organization': person.organization.pk,
    }])
    if response.status_code != 200:
        print(f"Response status: {response.status_code}, content: {response.content}")
    assert response.status_code == 200

    assert_log_entry_created(person, 'wagtail.edit', plan_admin_person.user, plan)


def test_person_delete_creates_log_entry(
    api_client, plan, plan_admin_person, person_factory
):
    """Test that deleting a person creates a PlanScopedModelLogEntry with action='wagtail.delete'."""
    api_client.force_login(plan_admin_person.user)

    person = person_factory(first_name='Person', last_name='ToDelete', organization=plan.organization)
    person_pk = person.pk

    url = reverse('person-detail', kwargs={'pk': person_pk}) + f'?plan={plan.identifier}'
    response = api_client.delete(url)
    assert response.status_code == 204

    assert not Person.objects.filter(pk=person_pk).exists()

    content_type = ContentType.objects.get_for_model(Person, for_concrete_model=False)
    log_entry = PlanScopedModelLogEntry.objects.filter(
        content_type=content_type,
        object_id=str(person_pk),
        action='wagtail.delete',
        plan=plan
    ).first()
    assert log_entry is not None, f"Expected log entry for deleted person {person_pk}"
    assert log_entry.user_id == plan_admin_person.user.pk


def test_bulk_person_post_creates_individual_log_entries(
        api_client, plan, person_list_url, plan_admin_person, person_factory):
    """Test that bulk POST of persons creates individual PlanScopedModelLogEntry for each person."""
    api_client.force_login(plan_admin_person.user)

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()

    response = api_client.post(person_list_url + f'?plan={plan.identifier}', data=[
        {'first_name': 'Bulk', 'last_name': 'Person 1', 'email': 'bulk1@example.com', 'organization': plan.organization.pk},
        {'first_name': 'Bulk', 'last_name': 'Person 2', 'email': 'bulk2@example.com', 'organization': plan.organization.pk},
        {'first_name': 'Bulk', 'last_name': 'Person 3', 'email': 'bulk3@example.com', 'organization': plan.organization.pk},
    ])
    assert response.status_code == 201

    assert Person.objects.filter(email__startswith='bulk').count() == 3

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries, got {final_log_count - initial_log_count}"


def test_bulk_person_put_creates_individual_log_entries(
        api_client, plan, plan_admin_person, person_factory):
    """Test that bulk PUT of persons creates individual PlanScopedModelLogEntry for each person."""
    api_client.force_login(plan_admin_person.user)
    persons = [
        person_factory(
            first_name=f'Original{i}',
            last_name=f'Person{i}',
            email=f'person-{i}@example.com',
            organization=plan.organization,
        )
        for i in range(1, 4)
    ]

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()

    data = [
        {
            'id': person.id,
            'first_name': f'Updated{person.first_name}',
            'last_name': person.last_name,
            'email': person.email,
            'organization': person.organization.pk,
        }
        for person in persons
    ]

    response = api_client.put(person_list_url + f'?plan={plan.identifier}', data=data)
    assert response.status_code == 200

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries for bulk update, got {final_log_count - initial_log_count}"

    for person in persons:
        total_logs = count_log_entries(instance=person, plan=plan)
        assert total_logs >= 1, f"Expected at least 1 log entry for person {person.email}"
