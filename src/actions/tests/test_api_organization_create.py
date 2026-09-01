from __future__ import annotations

from django.urls import reverse

import pytest

from actions.tests.factories import ActionContactFactory, ActionFactory, PlanFactory
from orgs.models import Organization
from orgs.tests.factories import OrganizationFactory
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def organization_list_url():
    return reverse('organization-list')


def test_organization_list_unauthenticated_with_plan_returns_403(api_client, organization_list_url):
    plan = PlanFactory.create()
    OrganizationFactory.create()
    organization = Organization.objects.first()
    assert organization
    plan.related_organizations.add(organization)

    api_client.logout()
    response = api_client.get(organization_list_url, data={'plan': plan.identifier})
    assert response.status_code == 403


def test_organization_list_unauthorized_user_for_plan_returns_403(api_client, organization_list_url):
    admin_plan = PlanFactory.create()
    admin_person = PersonFactory.create(
        organization=admin_plan.organization,
        general_admin_plans=[admin_plan],
    )

    other_plan = PlanFactory.create()
    OrganizationFactory.create()
    organization = Organization.objects.last()
    assert organization
    other_plan.related_organizations.add(organization)

    api_client.force_login(admin_person.user)
    response = api_client.get(organization_list_url, data={'plan': other_plan.identifier})
    assert response.status_code == 403


def test_organization_list_authorized_user_for_plan_returns_200(api_client, organization_list_url):
    plan = PlanFactory.create()
    admin_person = PersonFactory.create(
        organization=plan.organization,
        general_admin_plans=[plan],
    )

    api_client.force_login(admin_person.user)
    response = api_client.get(organization_list_url, data={'plan': plan.identifier})
    assert response.status_code == 200


def test_organization_list_contact_person_for_plan_returns_200(api_client, organization_list_url):
    # Contact persons are not general admins but should still be able to read
    # the plan's related organizations so the action grid can render its
    # responsible-party columns for them.
    plan = PlanFactory.create()
    action = ActionFactory.create(plan=plan)
    contact_person = PersonFactory.create(organization=plan.organization)
    ActionContactFactory.create(action=action, person=contact_person)

    api_client.force_login(contact_person.user)
    response = api_client.get(organization_list_url, data={'plan': plan.identifier})
    assert response.status_code == 200


def test_create_organization_unauthorized_for_plan_returns_403(api_client, organization_list_url):
    admin_plan = PlanFactory.create()
    admin_person = PersonFactory.create(
        organization=admin_plan.organization,
        general_admin_plans=[admin_plan],
    )

    other_plan = PlanFactory.create()

    api_client.force_login(admin_person.user)
    response = api_client.post(
        organization_list_url,
        data={'name': 'Sneaky Org', 'parent': None, 'left_sibling': None},
        QUERY_STRING=f'plan={other_plan.identifier}',
    )
    assert response.status_code == 403


def test_create_organization_gets_primary_language_from_plan_query_param(api_client, organization_list_url):
    plan = PlanFactory.create(primary_language='fi')
    admin_person = PersonFactory.create(
        organization=plan.organization,
        general_admin_plans=[plan],
    )
    api_client.force_login(admin_person.user)

    response = api_client.post(
        organization_list_url,
        data={'name': 'New Org', 'parent': None, 'left_sibling': None},
        QUERY_STRING=f'plan={plan.identifier}',
    )
    assert response.status_code == 201, response.json_data
    org = Organization.objects.get(pk=response.json_data['id'])
    assert org.primary_language == 'fi'
    assert plan.related_organizations.filter(pk=org.pk).exists()


def test_create_organization_falls_back_to_active_admin_plan(api_client, organization_list_url):
    plan = PlanFactory.create(primary_language='sv')
    admin_person = PersonFactory.create(
        organization=plan.organization,
        general_admin_plans=[plan],
    )
    api_client.force_login(admin_person.user)

    response = api_client.post(
        organization_list_url,
        data={'name': 'Fallback Org', 'parent': None, 'left_sibling': None},
    )
    assert response.status_code == 201, response.json_data
    org = Organization.objects.get(pk=response.json_data['id'])
    assert org.primary_language == 'sv'
    assert plan.related_organizations.filter(pk=org.pk).exists()


def test_create_organization_explicit_language_overrides_plan_query_param(api_client, organization_list_url):
    plan = PlanFactory.create(primary_language='fi')
    admin_person = PersonFactory.create(
        organization=plan.organization,
        general_admin_plans=[plan],
    )
    api_client.force_login(admin_person.user)

    response = api_client.post(
        organization_list_url,
        data={'name': 'Explicit Org', 'parent': None, 'left_sibling': None, 'primary_language': 'de'},
        QUERY_STRING=f'plan={plan.identifier}',
    )
    assert response.status_code == 201, response.json_data
    org = Organization.objects.get(pk=response.json_data['id'])
    assert org.primary_language == 'de'


def test_create_organization_explicit_language_overrides_active_admin_plan(api_client, organization_list_url):
    plan = PlanFactory.create(primary_language='sv')
    admin_person = PersonFactory.create(
        organization=plan.organization,
        general_admin_plans=[plan],
    )
    api_client.force_login(admin_person.user)

    response = api_client.post(
        organization_list_url,
        data={'name': 'Explicit Org 2', 'parent': None, 'left_sibling': None, 'primary_language': 'en'},
    )
    assert response.status_code == 201, response.json_data
    org = Organization.objects.get(pk=response.json_data['id'])
    assert org.primary_language == 'en'


def test_create_organization_rejects_invalid_language_choice(api_client, organization_list_url):
    plan = PlanFactory.create(primary_language='fi')
    admin_person = PersonFactory.create(
        organization=plan.organization,
        general_admin_plans=[plan],
    )
    api_client.force_login(admin_person.user)

    response = api_client.post(
        organization_list_url,
        data={'name': 'Bad Lang Org', 'parent': None, 'left_sibling': None, 'primary_language': 'xx-invalid'},
        QUERY_STRING=f'plan={plan.identifier}',
    )
    assert response.status_code == 400


def test_create_organization_rejects_too_long_language_code(api_client, organization_list_url):
    plan = PlanFactory.create(primary_language='fi')
    admin_person = PersonFactory.create(
        organization=plan.organization,
        general_admin_plans=[plan],
    )
    api_client.force_login(admin_person.user)

    response = api_client.post(
        organization_list_url,
        data={'name': 'Long Lang Org', 'parent': None, 'left_sibling': None, 'primary_language': 'a' * 9},
        QUERY_STRING=f'plan={plan.identifier}',
    )
    assert response.status_code == 400


def test_update_organization_preserves_primary_language_when_omitted(api_client, organization_list_url):
    plan = PlanFactory.create(primary_language='fi')
    admin_person = PersonFactory.create(
        organization=plan.organization,
        general_admin_plans=[plan],
    )
    api_client.force_login(admin_person.user)

    # Create an org with 'de' language
    response = api_client.post(
        organization_list_url,
        data={'name': 'Org To Update', 'parent': None, 'left_sibling': None, 'primary_language': 'de'},
        QUERY_STRING=f'plan={plan.identifier}',
    )
    assert response.status_code == 201, response.json_data
    org_id = response.json_data['id']
    org_uuid = response.json_data['uuid']

    # PATCH without primary_language — it should stay 'de'
    detail_url = reverse('organization-detail', kwargs={'pk': org_id})
    response = api_client.patch(
        detail_url,
        data={'id': org_id, 'uuid': org_uuid, 'name': 'Renamed Org', 'parent': None, 'left_sibling': None},
    )
    assert response.status_code == 200, response.json_data
    org = Organization.objects.get(pk=org_id)
    assert org.name == 'Renamed Org'
    assert org.primary_language == 'de'
