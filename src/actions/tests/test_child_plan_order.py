from __future__ import annotations

from django.urls import reverse

import pytest

from actions.models import Plan
from actions.tests.factories import PlanFactory
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db


def _reorder_url(parent: Plan, child: Plan, position: int) -> str:
    return reverse('actions_plan_reorder_child', args=(parent.pk, child.pk)) + f'?position={position}'


def _children(parent: Plan) -> list[Plan]:
    return list(Plan.objects.qs.filter(parent=parent).in_hierarchy_order())


@pytest.fixture
def children(plan):
    return [PlanFactory.create(parent=plan) for _ in range(3)]


def test_unordered_children_follow_creation_time(plan, children):
    assert _children(plan) == children


def test_reorder_moves_child_and_new_children_go_last(client, plan_admin_user, plan, children):
    first, second, third = children
    client.force_login(plan_admin_user)

    response = client.post(_reorder_url(plan, third, 0))

    assert response.status_code == 200
    new_child = PlanFactory.create(parent=plan)
    assert _children(plan) == [third, first, second, new_child]


def test_related_plans_list_parent_before_ordered_siblings(client, plan_admin_user, plan, children):
    first, second, third = children
    client.force_login(plan_admin_user)
    client.post(_reorder_url(plan, first, 2))

    related = list(first.get_all_related_plans().in_hierarchy_order())

    assert related == [plan, second, third]


def test_reorder_requires_general_admin_of_parent(client, plan, children):
    other_admin = PersonFactory.create(general_admin_plans=[children[0]]).user
    client.force_login(other_admin)

    response = client.post(_reorder_url(plan, children[2], 0))

    assert response.status_code != 200
    assert _children(plan) == children


def test_edit_page_lists_children(client, plan_admin_user, plan, children):
    client.force_login(plan_admin_user)

    response = client.get(reverse('actions_plan_modeladmin_edit', args=(plan.pk,)))

    assert response.status_code == 200
    for child in children:
        assert f'data-w-orderable-item-id="{child.pk}"' in response.content.decode()
