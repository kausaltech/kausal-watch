from __future__ import annotations

import pytest
from django.urls import reverse
from itertools import permutations
from typing import Iterable, List

from actions.api import ActionSerializer, OrganizationSerializer
from actions.tests.factories import ActionFactory
from aplans.tests.tree import Tree, parse_tree_string
from orgs.models import Organization
from orgs.tests.factories import OrganizationFactory

pytestmark = pytest.mark.django_db


def orgs_to_trees(roots: Iterable[Organization], indent=0):
    result: List[Tree] = []
    for root in roots:
        tree = Tree(root.name, indent)
        for child in orgs_to_trees(root.get_children(), indent + 4):
            tree.add_child(child)
        result.append(tree)
    return result


def tree_to_org(tree: Tree, parent: Organization | None=None):
    org = OrganizationFactory.create(name=tree.name, abbreviation=tree.name, parent=parent)
    for child in tree.children:
        tree_to_org(child, org)
    return org


@pytest.fixture
def org_hierarchy():
    trees = parse_tree_string("""
        1
        2
            2.1
            2.2
        3
            3.1
            3.2
            3.3
    """)
    return [tree_to_org(tree) for tree in trees]


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


def assert_org_hierarchy(expected_hierarchy: str):
    actual_roots = Organization.get_root_nodes()
    actual = orgs_to_trees(actual_roots)
    expected = parse_tree_string(expected_hierarchy)
    # We could use this, but comparing the values as strings produces nicer error messages
    # assert len(actual) == len(expected)
    # assert all(a.equals(e) for (a, e) in zip(actual, expected))
    actual_str = ''.join(str(tree) for tree in actual)
    expected_str = ''.join(str(tree) for tree in expected)
    assert actual_str == expected_str


def update_org_hierarchy(goal_string: str):
    # Only handles moving subtrees around for now
    uuid_for_name: dict[str, str | None]  = {'<dummy>': None}
    goal = Tree('<dummy>', 0)
    for root in parse_tree_string(goal_string, reset_indent=False):
        root.reset_indent(4)
        goal.add_child(root)
        for node in root.traverse():
            uuid_for_name[node.name] = str(Organization.objects.get(name=node.name).uuid)
    current = Tree('<dummy>', 0)
    for child in orgs_to_trees(Organization.get_root_nodes(), 4):
        current.add_child(child)
    serializer_input = []
    for goal_node in goal.traverse():
        current_node = current.get_node(goal_node.name)
        assert current_node
        changed_fields = []
        for field in ('parent', 'left_sibling'):
            current_value = getattr(current_node, field)
            current_value = current_value.name if current_value else None
            goal_value = getattr(goal_node, field)
            goal_value = goal_value.name if goal_value else None
            if current_value != goal_value:
                changed_fields.append(field)
        if changed_fields:
            node_data = OrganizationSerializer(Organization.objects.get(name=goal_node.name)).data
            for field in changed_fields:
                goal_value = getattr(goal_node, field)
                goal_uuid_str = uuid_for_name[goal_value.name] if goal_value else None
                assert node_data[field] != goal_uuid_str
                node_data[field] = goal_uuid_str if goal_uuid_str else None
            serializer_input.append(node_data)
    serializer = OrganizationSerializer(many=True, data=serializer_input, instance=Organization.objects.all())
    assert serializer.is_valid()
    serializer.save()


def test_organization_bulk_serializer_move_org1_after_org2(org_hierarchy):
    expected = """
        2
            2.1
            2.2
        1
        3
            3.1
            3.2
            3.3
    """
    update_org_hierarchy(expected)
    assert_org_hierarchy(expected)


def test_organization_bulk_serializer_move_org1_after_org21(org_hierarchy):
    expected = """
        2
            2.1
            1
            2.2
        3
            3.1
            3.2
            3.3
    """
    update_org_hierarchy(expected)
    assert_org_hierarchy(expected)


def test_organization_bulk_serializer_move_org22_after_org3(org_hierarchy):
    expected = """
        1
        2
            2.1
        3
            3.1
            3.2
            3.3
        2.2
    """
    update_org_hierarchy(expected)
    assert_org_hierarchy(expected)


def test_organization_bulk_serializer_move_org3_below_org22(org_hierarchy):
    expected = """
        1
        2
            2.1
            2.2
                3
                    3.1
                    3.2
                    3.3
    """
    update_org_hierarchy(expected)
    assert_org_hierarchy(expected)


@pytest.mark.parametrize('order', permutations(range(3)))
def test_organization_bulk_serializer_move_children_of_org3(org_hierarchy, order):
    expected = f"""
        1
        2
            2.1
            2.2
        3
            3.{order[0]+1}
            3.{order[1]+1}
            3.{order[2]+1}
    """
    update_org_hierarchy(expected)
    assert_org_hierarchy(expected)


@pytest.mark.parametrize('order', permutations(range(3)))
def test_organization_bulk_serializer_move_roots(org_hierarchy, order):
    subtrees = [
        """
        1
        """,
        """
        2
            2.1
            2.2
        """,
        """
        3
            3.1
            3.2
            3.3
        """,
    ]
    expected = subtrees[order[0]] + subtrees[order[1]] + subtrees[order[2]]
    update_org_hierarchy(expected)
    assert_org_hierarchy(expected)


def test_category_api_get(api_client, category_list_url, category):
    response = api_client.get(category_list_url)
    data = response.json_data
    assert data['count'] == 1
    assert len(data['results']) == 1

    obj = data['results'][0]
    assert obj['name'] == category.name
    assert obj['identifier'] == category.identifier
