import pytest
from django.urls import reverse
from orgs.tests.factories import OrganizationFactory
from orgs.models import Organization


pytestmark = pytest.mark.django_db


def test_plan_api_get(api_client, plan_list_url, plan):
    response = api_client.get(plan_list_url)
    data = response.json_data
    assert data['count'] == 1
    assert len(data['results']) == 1

    obj = data['results'][0]
    assert obj['name'] == plan.name
    assert obj['identifier'] == plan.identifier
    # assert obj['image_url'] is None

    """
    schedule = ActionSchedule.objects.create(
        plan=plan, name='next year', begins_at='2019-01-01', ends_at='2019-12-31'
    )

    response = api_client.get(
        plan_list_url,
        data={'include': 'action_schedules'}
    )
    data = response.json_data
    assert data['count'] == 1
    assert len(data['included']) == 1
    assert data['included'][0]['attributes']['name'] == schedule.name
    assert data['included'][0]['id'] == str(schedule.id)
    """


def test_action_api_get(api_client, action_list_url, action):
    response = api_client.get(action_list_url)
    data = response.json_data
    assert data['count'] == 1
    assert len(data['results']) == 1

    obj = data['results'][0]
    assert obj['name'] == action.name
    assert obj['identifier'] == action.identifier
    assert obj['plan'] == action.plan_id


PERSON_COUNT = 10


def test_person_api_get_not_authenticated(api_client, person_list_url, action_contact_factory):
    persons = [action_contact_factory().person for _ in range(0, PERSON_COUNT)]
    response = api_client.get(person_list_url)
    data = response.json_data
    assert len(data['results']) == PERSON_COUNT

    for person in persons:
        obj = next(x for x in data['results'] if x['id'] == person.id)
        assert obj['first_name'] == person.first_name
        assert obj['last_name'] == person.last_name
        # Important! The email addresses should not be exposed without authorization
        assert 'email' not in obj


def test_person_api_get_for_plan_unauthenticated(api_client, person_list_url, plan, person):
    api_client.logout()
    response = api_client.get(person_list_url, data={'plan': plan.identifier})
    data = response.json_data
    assert response.status_code == 403
    keys = data.keys()
    assert len(keys) == 1 and 'detail' in keys


def test_person_api_get_authenticated_and_authorized_for_single_plan(
        client, person_list_url, api_client,
        plan_factory, person_factory, action_contact_factory):

    plan_of_admin_person = plan_factory()
    admin_person = person_factory(general_admin_plans=[plan_of_admin_person])

    plan_not_accessible_by_admin_person = plan_factory()

    persons_found = [action_contact_factory(action__plan=plan_of_admin_person).person for _ in range(0, PERSON_COUNT)]
    person_not_found = action_contact_factory(action__plan=plan_not_accessible_by_admin_person).person

    api_client.force_login(admin_person.user)

    response = api_client.get(person_list_url, {'plan': plan_of_admin_person.identifier})
    data = response.json_data

    assert len(data['results']) == PERSON_COUNT
    for person_found in persons_found:
        result_person_data = next(x for x in data['results'] if x['id'] == person_found.id)
        assert result_person_data['first_name'] == person_found.first_name
        assert result_person_data['last_name'] == person_found.last_name
        assert result_person_data['last_name'] == person_found.last_name

    assert person_not_found.id not in (d['id'] for d in data['results'])


def test_person_api_get_authenticated_and_unauthorized(
        client, person_list_url, api_client, plan_factory,
        person_factory, action_contact_factory):

    admin_person = person_factory(general_admin_plans=[plan_factory()])

    plan_auth_fail = plan_factory()
    action_contact_factory(action__plan=plan_auth_fail)
    api_client.force_login(admin_person.user)

    response = api_client.get(person_list_url, {'plan': plan_auth_fail.identifier})
    data = response.json_data
    assert response.status_code == 403
    keys = data.keys()
    assert len(keys) == 1 and 'detail' in keys


def test_person_api_get_unknown_plan(
        client, person_list_url, api_client, plan_factory,
        person_factory, action_contact_factory):

    plan = plan_factory()
    admin_person = person_factory(general_admin_plans=[plan])
    action_contact_factory(action__plan=plan)
    api_client.force_login(admin_person.user)

    response = api_client.get(person_list_url, {'plan': '__non-existent__'})
    data = response.json_data
    assert response.status_code == 404
    keys = data.keys()
    assert len(keys) == 1 and 'detail' in keys


def test_action_api_post_unauthenticated(
        api_client, action_list_url, action):
    response = api_client.post(action_list_url, {'name': 'foo'})
    assert response.status_code == 401


def test_action_api_put_unauthenticated(
        api_client, action, action_detail_url):
    response = api_client.put(action_detail_url, data={
        'id': action.pk,
        'identifier': action.identifier,
        'name': 'renamed'
    })
    assert response.status_code == 401


def test_action_post_as_contact_person_denied(
        api_client, action, action_list_url, action_contact_factory):
    contact = action_contact_factory()
    user = contact.person.user
    api_client.force_login(user)
    response = api_client.post(action_list_url, data={'name': 'bar'})
    assert response.status_code == 403


def test_action_put_as_contact_person_denied_for_other_action(
        api_client, action, action_detail_url, action_contact_factory):
    contact = action_contact_factory()
    user = contact.person.user
    assert not user.is_superuser
    assert action.plan not in user.person.general_admin_plans.all()
    assert contact.action != action
    api_client.force_login(user)
    response = api_client.put(action_detail_url, data={
        'identifier': 'ID-1',
        'id': action.id,
        'name': 'bar'})
    assert response.status_code == 403


def test_action_put_as_contact_person_allowed_for_own_action(
        api_client, plan, action_contact_factory):
    contact = action_contact_factory(action__plan=plan)
    user = contact.person.user
    assert not user.is_superuser
    assert contact.action.plan not in user.person.general_admin_plans.all()
    api_client.force_login(user)
    url = reverse('action-detail', kwargs={'plan_pk': plan.pk, 'pk': contact.action.pk})
    response = api_client.put(url, data={
        'identifier': 'ID-1',
        'id': contact.action.id,
        'name': 'bar'})
    assert response.status_code == 200


def test_action_post_as_plan_admin_allowed(
        api_client, plan, action_list_url, plan_factory, person_factory):
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)
    response = api_client.post(action_list_url, data={
        'identifier': 'ID-1',
        'name': '_name_',
        'plan': plan.pk})
    assert response.status_code == 201


def test_action_put_as_plan_admin_allowed(
        api_client, plan, action, action_detail_url, person_factory):
    plan_of_admin_person = action.plan
    admin_person = person_factory(general_admin_plans=[plan_of_admin_person])
    api_client.force_login(admin_person.user)
    response = api_client.put(action_detail_url, data={
        'id': action.pk,
        'identifier': 'ID-1',
        'name': 'bar',
        'plan': plan_of_admin_person.pk})
    assert response.status_code == 200


def test_action_responsible_party_patch(
        api_client, action, action_detail_url, plan_admin_user):
    plan = action.plan
    plan_org = plan.organization
    other_org = OrganizationFactory.create()

    api_client.force_login(plan_admin_user)
    # Check that normal case works
    response = api_client.patch(action_detail_url, data={
        'responsible_parties': [{'organization': plan_org.pk, 'role': None}],
    })
    assert response.status_code == 200

    assert action.responsible_parties.count() == 1
    assert action.responsible_parties.first().organization == plan_org

    # Ensure that only orgs that are available for the plan
    # can be selected.
    response = api_client.patch(action_detail_url, data={
        'responsible_parties': [{'organization': other_org.pk, 'role': None}],
    })
    assert response.status_code == 400

    response = api_client.patch(action_detail_url, data={
        'responsible_parties': [],
    })
    assert response.status_code == 200
    assert action.responsible_parties.count() == 0

    response = api_client.patch(action_detail_url, data={
        'responsible_parties': [{'organization': 'abc', 'role': None}],
    })
    assert response.status_code == 400

    response = api_client.patch(action_detail_url, data={
        'responsible_parties': {'organization': plan_org.pk, 'role': None},
    })
    assert response.status_code == 400


def test_openapi_schema(api_client, openapi_url):
    resp = api_client.get(openapi_url)
    assert resp.status_code == 200
