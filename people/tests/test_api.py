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
        api_client, plan, person_list_url, person_factory):
    """Test that creating a person creates a PlanScopedModelLogEntry with action='wagtail.create'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    response = api_client.post(person_list_url + f'?plan={plan.identifier}', data={
        'first_name': 'Test',
        'last_name': 'Person',
        'email': 'test.person@example.com',
    })
    assert response.status_code == 201

    created_person = Person.objects.get(email='test.person@example.com')
    assert_log_entry_created(created_person, 'wagtail.create', admin_person.user, plan)


def test_person_put_creates_log_entry(
        api_client, plan, person_list_url, person_factory):
    """Test that updating a person creates a PlanScopedModelLogEntry with action='wagtail.edit'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    person = person_factory(first_name='Original', last_name='Name')
    person_detail_url = reverse('person-detail', kwargs={'pk': person.pk})

    response = api_client.put(person_detail_url + f'?plan={plan.identifier}', data={
        'first_name': 'Updated',
        'last_name': 'Name',
        'email': person.email,
    })
    assert response.status_code == 200

    assert_log_entry_created(person, 'wagtail.edit', admin_person.user, plan)


def test_person_delete_creates_log_entry(
        api_client, plan, person_factory):
    """Test that deleting a person creates a PlanScopedModelLogEntry with action='wagtail.delete'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    person = person_factory(first_name='Person', last_name='ToDelete')
    person_pk = person.pk
    person_detail_url = reverse('person-detail', kwargs={'pk': person.pk})

    response = api_client.delete(person_detail_url + f'?plan={plan.identifier}')
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
    assert log_entry.user_id == admin_person.user.pk


def test_bulk_person_post_creates_individual_log_entries(
        api_client, plan, person_list_url, person_factory):
    """Test that bulk POST of persons creates individual PlanScopedModelLogEntry for each person."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()

    response = api_client.post(person_list_url + f'?plan={plan.identifier}', data=[
        {'first_name': 'Bulk', 'last_name': 'Person 1', 'email': 'bulk1@example.com'},
        {'first_name': 'Bulk', 'last_name': 'Person 2', 'email': 'bulk2@example.com'},
        {'first_name': 'Bulk', 'last_name': 'Person 3', 'email': 'bulk3@example.com'},
    ])
    assert response.status_code == 201

    assert Person.objects.filter(email__startswith='bulk').count() == 3

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries, got {final_log_count - initial_log_count}"


def test_bulk_person_put_creates_individual_log_entries(
        api_client, plan, person_list_url, person_factory):
    """Test that bulk PUT of persons creates individual PlanScopedModelLogEntry for each person."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    persons = [
        person_factory(first_name=f'Original{i}', last_name=f'Person{i}', email=f'person{i}@example.com')
        for i in range(1, 4)
    ]

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()

    data = []
    for person in persons:
        serialized = PersonSerializer(person).data
        serialized['first_name'] = f'Updated{person.first_name}'
        data.append(serialized)

    response = api_client.put(person_list_url + f'?plan={plan.identifier}', data=data)
    assert response.status_code == 200

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries for bulk update, got {final_log_count - initial_log_count}"

    for person in persons:
        total_logs = count_log_entries(instance=person, plan=plan)
        assert total_logs >= 1, f"Expected at least 1 log entry for person {person.email}"
