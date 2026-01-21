from __future__ import annotations

from itertools import permutations

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

import pytest

from actions.api import ActionSerializer
from actions.tests.factories import ActionContactFactory, ActionFactory, PlanFactory
from orgs.tests.factories import OrganizationFactory, OrganizationPlanAdminFactory
from people.tests.factories import PersonFactory
from actions.models import Action
from actions.api import ActionSerializer, ActionTaskSerializer, CategorySerializer
from actions.models import Action, ActionTask, Category
from actions.api import ActionSerializer
from actions.models import Action
from actions.tests.factories import ActionContactFactory, ActionFactory
from actions.tests.utils import assert_log_entry_created, count_log_entries
from audit_logging.models import PlanScopedModelLogEntry
from orgs.tests.factories import OrganizationFactory
from actions.tests.factories import ActionContactFactory, ActionFactory
from orgs.tests.factories import OrganizationFactory

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
    persons = [action_contact_factory().person for _ in range(PERSON_COUNT)]
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
    assert len(keys) == 1
    assert 'detail' in keys


@pytest.mark.parametrize('admin_type', ['plan_admin', 'organization_plan_admin'])
def test_person_api_get_authenticated_and_authorized_for_single_plan(
    client, person_list_url, api_client, admin_type
):
    plan_of_admin_person = PlanFactory.create()

    match admin_type:
        case 'plan_admin':
            admin_person = PersonFactory.create(
                organization=plan_of_admin_person.organization,
                general_admin_plans=[plan_of_admin_person],
            )
        case 'organization_plan_admin':
            admin_person = PersonFactory.create(organization=plan_of_admin_person.organization)
            OrganizationPlanAdminFactory.create(
                person=admin_person,
                organization=plan_of_admin_person.organization,
                plan=plan_of_admin_person
            )
        case _:
            pytest.fail('Unexpected admin_type')

    plan_not_accessible_by_admin_person = PlanFactory.create()

    persons_found = [ActionContactFactory.create(action__plan=plan_of_admin_person).person for _ in range(PERSON_COUNT)]
    person_not_found = ActionContactFactory.create(action__plan=plan_not_accessible_by_admin_person).person

    api_client.force_login(admin_person.user)

    response = api_client.get(person_list_url, {'plan': plan_of_admin_person.identifier})
    data = response.json_data
    assert response.status_code == 200

    assert len(data['results']) == PERSON_COUNT + 1  # +1 for the admin themselves
    for person_found in (*persons_found, admin_person):
        result_person_data = next(x for x in data['results'] if x['id'] == person_found.id)
        assert result_person_data['first_name'] == person_found.first_name
        assert result_person_data['last_name'] == person_found.last_name
        assert result_person_data['email'] == person_found.email

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
    assert len(keys) == 1
    assert 'detail' in keys


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
    assert len(keys) == 1
    assert 'detail' in keys


def test_action_api_post_unauthenticated(
        api_client, action_list_url, action):
    response = api_client.post(action_list_url, {'name': 'foo'})
    assert response.status_code == 401


def test_action_api_put_unauthenticated(
        api_client, action, action_detail_url):
    response = api_client.put(action_detail_url, data={
        'id': action.pk,
        'identifier': action.identifier,
        'name': 'renamed',
    })
    assert response.status_code == 401


def test_action_post_as_contact_person_denied(api_client, action_list_url):
    contact = ActionContactFactory.create()
    user = contact.person.user
    api_client.force_login(user)
    response = api_client.post(action_list_url, data={'name': 'bar'})
    assert response.status_code == 403


def test_action_put_as_contact_person_denied_for_other_action(api_client, action, action_detail_url):
    contact = ActionContactFactory.create(action__plan=action.plan)
    user = contact.person.user
    assert user
    assert not user.is_superuser
    assert action.plan not in user.person.general_admin_plans.all()
    assert contact.action != action
    api_client.force_login(user)
    response = api_client.put(action_detail_url, data={
        'identifier': 'ID-1',
        'id': action.id,
        'name': 'bar',
    })
    assert response.status_code == 403


def test_action_bulk_put_as_contact_person_denied_for_other_action(api_client, action, action_list_url):
    contact = ActionContactFactory.create(action__plan=action.plan)
    user = contact.person.user
    assert user
    assert not user.is_superuser
    assert action.plan not in user.person.general_admin_plans.all()
    assert contact.action != action
    api_client.force_login(user)
    response = api_client.put(action_list_url, data=[{
        'identifier': 'ID-1',
        'id': action.id,
        'name': 'bar',
    }])
    assert response.status_code == 403


def test_action_put_as_contact_person_allowed_for_own_action(api_client, plan):
    contact = ActionContactFactory.create(action__plan=plan)
    user = contact.person.user
    assert user
    assert not user.is_superuser
    assert contact.action.plan not in user.person.general_admin_plans.all()
    api_client.force_login(user)
    url = reverse('action-detail', kwargs={'plan_pk': plan.pk, 'pk': contact.action.pk})
    response = api_client.put(url, data={
        'identifier': 'ID-1',
        'id': contact.action.id,
        'name': 'bar'})
    assert response.status_code == 200


def test_action_bulk_put_as_contact_person_allowed_for_own_action(api_client, plan, action_list_url):
    contact = ActionContactFactory.create(action__plan=plan)
    user = contact.person.user
    assert user
    assert not user.is_superuser
    assert contact.action.plan not in user.person.general_admin_plans.all()
    api_client.force_login(user)
    response = api_client.put(action_list_url, data=[{
        'identifier': 'ID-1',
        'id': contact.action.id,
        'name': 'bar'}])
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

    # Verify that a log entry was created for the new action
    created_action = Action.objects.get(identifier='ID-1', plan=plan)
    assert_log_entry_created(created_action, 'wagtail.create', admin_person.user, plan)


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

    # Verify that a log entry was created for the updated action
    action.refresh_from_db()
    assert_log_entry_created(action, 'wagtail.edit', admin_person.user, plan_of_admin_person)


def test_action_responsible_party_patch(
        api_client, action, action_detail_url, plan_admin_user):
    plan = action.plan
    plan_org = plan.organization
    other_org = OrganizationFactory.create()

    api_client.force_login(plan_admin_user)

    # Check that normal case works
    initial_log_count = count_log_entries(instance=action, action='wagtail.edit', plan=plan)
    response = api_client.patch(action_detail_url, data={
        'responsible_parties': [{'organization': plan_org.pk, 'role': None}],
    })
    assert response.status_code == 200

    assert action.responsible_parties.count() == 1
    assert action.responsible_parties.first().organization == plan_org

    # Verify log entry was created for successful PATCH
    assert count_log_entries(instance=action, action='wagtail.edit', plan=plan) == initial_log_count + 1

    # Ensure that only orgs that are available for the plan
    # can be selected.
    response = api_client.patch(action_detail_url, data={
        'responsible_parties': [{'organization': other_org.pk, 'role': None}],
    })
    assert response.status_code == 400

    current_log_count = count_log_entries(instance=action, action='wagtail.edit', plan=plan)
    response = api_client.patch(action_detail_url, data={
        'responsible_parties': [],
    })
    assert response.status_code == 200
    assert action.responsible_parties.count() == 0

    # Verify log entry was created for second successful PATCH
    assert count_log_entries(instance=action, action='wagtail.edit', plan=plan) == current_log_count + 1

    response = api_client.patch(action_detail_url, data={
        'responsible_parties': [{'organization': 'abc', 'role': None}],
    })
    assert response.status_code == 400

    response = api_client.patch(action_detail_url, data={
        'responsible_parties': {'organization': plan_org.pk, 'role': None},
    })
    assert response.status_code == 400


def test_action_delete_creates_log_entry(
        api_client, plan, action_list_url, person_factory):
    """Test that deleting an action creates a PlanScopedModelLogEntry with action='wagtail.delete'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    # Create an action to delete
    action = ActionFactory.create(plan=plan, identifier='DELETE-ME')
    action_pk = action.pk
    action_detail_url = reverse('action-detail', kwargs={'plan_pk': plan.pk, 'pk': action.pk})

    # Delete the action
    response = api_client.delete(action_detail_url)
    assert response.status_code == 204

    # Verify the action was deleted
    assert not Action.objects.filter(pk=action_pk).exists()

    # Verify that a log entry was created for the deletion
    # Note: We need to create a temporary object with the same pk to use assert_log_entry_created
    # Or we can check directly
    content_type = ContentType.objects.get_for_model(Action, for_concrete_model=False)
    log_entry = PlanScopedModelLogEntry.objects.filter(
        content_type=content_type,
        object_id=str(action_pk),
        action='wagtail.delete',
        plan=plan
    ).first()
    assert log_entry is not None, f"Expected log entry for deleted action {action_pk}"
    assert log_entry.user_id == admin_person.user.pk


def test_openapi_schema(api_client, openapi_url):
    resp = api_client.get(openapi_url)
    assert resp.status_code == 200


def test_action_bulk_serializer_initial_order(plan):
    actions = [ActionFactory.create(plan=plan) for _ in range(4)]
    assert [action.order == i for i, action in enumerate(actions)]
    # Serialize these actions and use that as input for actually testing ActionSerializer initialized with `many=True`
    data = [ActionSerializer(action).data for action in actions]
    serializer = ActionSerializer(many=True, data=data, instance=plan.actions.all())
    assert serializer.is_valid()
    serializer.save()
    actions_after_save = list(plan.actions.all())
    assert actions_after_save == actions
    assert [a1.order == a2.order for a1, a2 in zip(actions_after_save, actions)]


@pytest.mark.parametrize('order', permutations(range(3)))
def test_action_bulk_serializer_reorder(plan, order):
    actions = [ActionFactory.create(plan=plan) for _ in range(len(order))]
    # Reorder actions
    actions = [actions[i] for i in order]
    for i, action in enumerate(actions):
        action.order = i
    data = [ActionSerializer(action).data for action in actions]
    # The left_sibling values are not according to our new order because they are taken from the persisted values, so we
    # need to fix them.
    prev_action_data = None
    for action_data in data:
        action_data['left_sibling'] = prev_action_data['uuid'] if prev_action_data else None
        action_data.pop('order')  # should work without that
        prev_action_data = action_data
    serializer = ActionSerializer(many=True, data=data, instance=plan.actions.all())
    assert serializer.is_valid()
    serializer.save()
    actions_after_save = list(plan.actions.all())
    assert actions_after_save == actions
    assert [a1.order == a2.order for a1, a2 in zip(actions_after_save, actions)]


def test_bulk_action_post_creates_individual_log_entries(
        api_client, plan, action_list_url, person_factory):
    """Test that bulk POST of actions creates individual PlanScopedModelLogEntry for each action."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()

    # Bulk create 3 actions
    response = api_client.post(action_list_url, data=[
        {'identifier': 'BULK-1', 'name': 'Action 1', 'plan': plan.pk},
        {'identifier': 'BULK-2', 'name': 'Action 2', 'plan': plan.pk},
        {'identifier': 'BULK-3', 'name': 'Action 3', 'plan': plan.pk},
    ])
    assert response.status_code == 201

    # Verify 3 actions were created
    assert Action.objects.filter(plan=plan, identifier__startswith='BULK-').count() == 3

    # Verify that 3 log entries were created (one for each action)
    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()
    assert final_log_count == initial_log_count + 3

    # Verify each action has its own log entry with correct object_id
    for identifier in ['BULK-1', 'BULK-2', 'BULK-3']:
        action = Action.objects.get(plan=plan, identifier=identifier)
        assert count_log_entries(instance=action, action='wagtail.create', plan=plan) == 1


def test_bulk_action_put_creates_individual_log_entries(
        api_client, plan, action_list_url, person_factory):
    """Test that bulk PUT of actions creates individual PlanScopedModelLogEntry for each action."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    # Create 3 actions to update
    actions = [
        ActionFactory.create(plan=plan, identifier=f'UPDATE-{i}', name=f'Original {i}')
        for i in range(1, 4)
    ]

    # Clear any existing log entries for these actions to have a clean count
    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()

    # Bulk update all 3 actions
    data = []
    for action in actions:
        serialized = ActionSerializer(action).data
        serialized['name'] = f'Updated {action.identifier}'
        data.append(serialized)

    response = api_client.put(action_list_url, data=data)
    assert response.status_code == 200

    # Verify that log entries were created for bulk update
    # Note: Based on current implementation, bulk updates create log entries with action='wagtail.edit'
    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()
    assert final_log_count > initial_log_count

    # Verify each action has at least one log entry
    for action in actions:
        action.refresh_from_db()
        # At minimum, there should be a wagtail.edit log entry
        total_logs = count_log_entries(instance=action, plan=plan)
        assert total_logs >= 1, f"Expected at least 1 log entry for action {action.identifier}"


def test_category_api_get(api_client, category_list_url, category):
    response = api_client.get(category_list_url)
    data = response.json_data
    assert data['count'] == 1
    assert len(data['results']) == 1

    obj = data['results'][0]
    assert obj['name'] == category.name
    assert obj['identifier'] == category.identifier


def test_category_post_creates_log_entry(
        api_client, plan, category_type, category_list_url, person_factory):
    """Test that creating a category creates a PlanScopedModelLogEntry with action='wagtail.create'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    response = api_client.post(category_list_url, data={
        'identifier': 'CAT-1',
        'name': 'Test Category',
        'type': category_type.pk,
        'parent': None
    })
    assert response.status_code == 201

    created_category = Category.objects.get(identifier='CAT-1', type=category_type)
    assert_log_entry_created(created_category, 'wagtail.create', admin_person.user, plan)


def test_category_put_creates_log_entry(
        api_client, plan, category_type, category_list_url, category_factory, person_factory):
    """Test that updating a category creates a PlanScopedModelLogEntry with action='wagtail.edit'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    category = category_factory(type=category_type, name='Original Name')
    category_detail_url = reverse('category-detail', kwargs={
        'plan_pk': plan.pk,
        'category_type_pk': category_type.pk,
        'pk': category.pk
    })

    response = api_client.put(category_detail_url, data={
        'identifier': category.identifier,
        'name': 'Updated Name',
        'type': category_type.pk,
        'parent': None
    })
    assert response.status_code == 200

    assert_log_entry_created(category, 'wagtail.edit', admin_person.user, plan)


def test_category_delete_creates_log_entry(
        api_client, plan, category_type, category_factory, person_factory):
    """Test that deleting a category creates a PlanScopedModelLogEntry with action='wagtail.delete'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    category = category_factory(type=category_type, identifier='DELETE-CAT')
    category_pk = category.pk
    category_detail_url = reverse('category-detail', kwargs={
        'plan_pk': plan.pk,
        'category_type_pk': category_type.pk,
        'pk': category.pk
    })

    response = api_client.delete(category_detail_url)
    assert response.status_code == 204

    assert not Category.objects.filter(pk=category_pk).exists()

    content_type = ContentType.objects.get_for_model(Category, for_concrete_model=False)
    log_entry = PlanScopedModelLogEntry.objects.filter(
        content_type=content_type,
        object_id=str(category_pk),
        action='wagtail.delete',
        plan=plan
    ).first()
    assert log_entry is not None, f"Expected log entry for deleted category {category_pk}"
    assert log_entry.user_id == admin_person.user.pk


def test_bulk_category_post_creates_individual_log_entries(
        api_client, plan, category_type, category_list_url, person_factory):
    """Test that bulk POST of categories creates individual PlanScopedModelLogEntry for each category."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()

    response = api_client.post(category_list_url, data=[
        {'identifier': 'BULK-CAT-1', 'name': 'Category 1', 'type': category_type.pk, 'parent': None},
        {'identifier': 'BULK-CAT-2', 'name': 'Category 2', 'type': category_type.pk, 'parent': None},
        {'identifier': 'BULK-CAT-3', 'name': 'Category 3', 'type': category_type.pk, 'parent': None},
    ])
    assert response.status_code == 201

    assert Category.objects.filter(type=category_type, identifier__startswith='BULK-CAT-').count() == 3

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries, got {final_log_count - initial_log_count}"


def test_bulk_category_put_creates_individual_log_entries(
        api_client, plan, category_type, category_list_url, category_factory, person_factory):
    """Test that bulk PUT of categories creates individual PlanScopedModelLogEntry for each category."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    categories = [
        category_factory(type=category_type, identifier=f'UPDATE-CAT-{i}', name=f'Original {i}')
        for i in range(1, 4)
    ]

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()

    data = []
    for category in categories:
        serialized = CategorySerializer(category).data
        serialized['name'] = f'Updated {category.identifier}'
        data.append(serialized)

    response = api_client.put(category_list_url, data=data)
    assert response.status_code == 200

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries for bulk update, got {final_log_count - initial_log_count}"

    for category in categories:
        total_logs = count_log_entries(instance=category, plan=plan)
        assert total_logs >= 1, f"Expected at least 1 log entry for category {category.identifier}"


def test_action_task_post_creates_log_entry(
        api_client, plan, action, action_task_list_url, person_factory):
    """Test that creating an action task creates a PlanScopedModelLogEntry with action='wagtail.create'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    response = api_client.post(action_task_list_url, data={
        'action': action.pk,
        'name': 'Test Task',
        'due_at': '2025-12-31',
        'state': 'not_started'
    })
    assert response.status_code == 201

    created_task = ActionTask.objects.get(action=action, name='Test Task')
    assert_log_entry_created(created_task, 'wagtail.create', admin_person.user, plan)


def test_action_task_put_creates_log_entry(
        api_client, plan, action, action_task_list_url, person_factory):
    """Test that updating an action task creates a PlanScopedModelLogEntry with action='wagtail.edit'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    task = ActionTask.objects.create(
        action=action,
        name='Original Task',
        due_at='2025-12-31',
        state='not_started'
    )
    task_detail_url = reverse('action-task-detail', kwargs={'plan_pk': plan.pk, 'pk': task.pk})

    response = api_client.put(task_detail_url, data={
        'action': action.pk,
        'name': 'Updated Task',
        'due_at': '2025-12-31',
        'state': 'in_progress'
    })
    assert response.status_code == 200

    assert_log_entry_created(task, 'wagtail.edit', admin_person.user, plan)


def test_action_task_delete_creates_log_entry(
        api_client, plan, action, person_factory):
    """Test that deleting an action task creates a PlanScopedModelLogEntry with action='wagtail.delete'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    task = ActionTask.objects.create(
        action=action,
        name='Task to Delete',
        due_at='2025-12-31',
        state='not_started'
    )
    task_pk = task.pk
    task_detail_url = reverse('action-task-detail', kwargs={'plan_pk': plan.pk, 'pk': task.pk})

    response = api_client.delete(task_detail_url)
    assert response.status_code == 204

    assert not ActionTask.objects.filter(pk=task_pk).exists()

    content_type = ContentType.objects.get_for_model(ActionTask, for_concrete_model=False)
    log_entry = PlanScopedModelLogEntry.objects.filter(
        content_type=content_type,
        object_id=str(task_pk),
        action='wagtail.delete',
        plan=plan
    ).first()
    assert log_entry is not None, f"Expected log entry for deleted action task {task_pk}"
    assert log_entry.user_id == admin_person.user.pk


def test_bulk_action_task_post_creates_individual_log_entries(
        api_client, plan, action, action_task_list_url, person_factory):
    """Test that bulk POST of action tasks creates individual PlanScopedModelLogEntry for each task."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()

    response = api_client.post(action_task_list_url, data=[
        {'action': action.pk, 'name': 'Task 1', 'due_at': '2025-12-31', 'state': 'not_started'},
        {'action': action.pk, 'name': 'Task 2', 'due_at': '2025-12-31', 'state': 'not_started'},
        {'action': action.pk, 'name': 'Task 3', 'due_at': '2025-12-31', 'state': 'not_started'},
    ])
    assert response.status_code == 201

    assert ActionTask.objects.filter(action=action, name__startswith='Task ').count() == 3

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries, got {final_log_count - initial_log_count}"


def test_bulk_action_task_put_creates_individual_log_entries(
        api_client, plan, action, action_task_list_url, person_factory):
    """Test that bulk PUT of action tasks creates individual PlanScopedModelLogEntry for each task."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    tasks = [
        ActionTask.objects.create(
            action=action,
            name=f'Original Task {i}',
            due_at='2025-12-31',
            state='not_started'
        )
        for i in range(1, 4)
    ]

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()

    data = [
        {
            'id': task.id,
            'name': task.name,
            'state': 'in_progress',
            'due_at': '2025-12-31',
            'action': action.pk,
        }
        for task in tasks
    ]

    response = api_client.put(action_task_list_url, data=data)
    assert response.status_code == 200, response.content

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries for bulk update, got {final_log_count - initial_log_count}"

    for task in tasks:
        total_logs = count_log_entries(instance=task, plan=plan)
        assert total_logs >= 1, f"Expected at least 1 log entry for task {task.name}"
