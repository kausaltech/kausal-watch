from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

import pytest

from actions.api import OrganizationSerializer
from actions.tests.utils import assert_log_entry_created, count_log_entries
from audit_logging.models import PlanScopedModelLogEntry
from orgs.models import Organization

pytestmark = pytest.mark.django_db


@pytest.fixture
def organization_list_url():
    return reverse('organization-list')


def test_organization_post_creates_log_entry(
        api_client, plan, organization_list_url, person_factory):
    """Test that creating an organization creates a PlanScopedModelLogEntry with action='wagtail.create'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    response = api_client.post(organization_list_url + f'?plan={plan.identifier}', data={
        'name': 'Test Organization',
        'abbreviation': 'TEST-ORG',
    })
    assert response.status_code == 201

    created_org = Organization.objects.get(name='Test Organization')
    assert_log_entry_created(created_org, 'wagtail.create', admin_person.user, plan)


def test_organization_put_creates_log_entry(
        api_client, plan, organization_list_url, organization_factory, person_factory):
    """Test that updating an organization creates a PlanScopedModelLogEntry with action='wagtail.edit'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    org = organization_factory(name='Original Name')
    org.related_plans.add(plan)
    organization_detail_url = reverse('organization-detail', kwargs={'pk': org.pk})

    response = api_client.put(organization_detail_url + f'?plan={plan.identifier}', data={
        'name': 'Updated Name',
        'abbreviation': org.abbreviation,
    })
    assert response.status_code == 200

    assert_log_entry_created(org, 'wagtail.edit', admin_person.user, plan)


def test_organization_delete_creates_log_entry(
        api_client, plan, organization_factory, person_factory):
    """Test that deleting an organization creates a PlanScopedModelLogEntry with action='wagtail.delete'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    org = organization_factory(name='Organization to Delete')
    org.related_plans.add(plan)
    org_pk = org.pk
    organization_detail_url = reverse('organization-detail', kwargs={'pk': org.pk})

    response = api_client.delete(organization_detail_url + f'?plan={plan.identifier}')
    assert response.status_code == 204

    assert not Organization.objects.filter(pk=org_pk).exists()

    content_type = ContentType.objects.get_for_model(Organization, for_concrete_model=False)
    log_entry = PlanScopedModelLogEntry.objects.filter(
        content_type=content_type,
        object_id=str(org_pk),
        action='wagtail.delete',
        plan=plan
    ).first()
    assert log_entry is not None, f"Expected log entry for deleted organization {org_pk}"
    assert log_entry.user_id == admin_person.user.pk


def test_bulk_organization_post_creates_individual_log_entries(
        api_client, plan, organization_list_url, person_factory):
    """Test that bulk POST of organizations creates individual PlanScopedModelLogEntry for each organization."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()

    response = api_client.post(organization_list_url + f'?plan={plan.identifier}', data=[
        {'name': 'Bulk Organization 1', 'abbreviation': 'BULK-ORG-1'},
        {'name': 'Bulk Organization 2', 'abbreviation': 'BULK-ORG-2'},
        {'name': 'Bulk Organization 3', 'abbreviation': 'BULK-ORG-3'},
    ])
    assert response.status_code == 201

    assert Organization.objects.filter(name__startswith='Bulk Organization ').count() == 3

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries, got {final_log_count - initial_log_count}"


def test_bulk_organization_put_creates_individual_log_entries(
        api_client, plan, organization_list_url, organization_factory, person_factory):
    """Test that bulk PUT of organizations creates individual PlanScopedModelLogEntry for each organization."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    orgs = [
        organization_factory(name=f'Original Organization {i}', abbreviation=f'ORG-{i}')
        for i in range(1, 4)
    ]
    for org in orgs:
        org.related_plans.add(plan)

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()

    data = []
    for org in orgs:
        serialized = OrganizationSerializer(org).data
        serialized['name'] = f'Updated {org.name}'
        data.append(serialized)

    response = api_client.put(organization_list_url + f'?plan={plan.identifier}', data=data)
    assert response.status_code == 200

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries for bulk update, got {final_log_count - initial_log_count}"

    for org in orgs:
        total_logs = count_log_entries(instance=org, plan=plan)
        assert total_logs >= 1, f"Expected at least 1 log entry for organization {org.name}"
