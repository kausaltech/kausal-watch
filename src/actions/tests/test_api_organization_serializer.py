from __future__ import annotations

from itertools import permutations

import pytest

from aplans.tests.tree import Tree, parse_tree_string

from actions.api import OrganizationSerializer
from orgs.models import Organization
from orgs.tests.fixtures import *
from orgs.tests.utils import assert_org_hierarchy, orgs_to_trees

pytestmark = pytest.mark.django_db


@pytest.fixture
def original_org_hierarchy(organization_hierarchy_factory):
    return organization_hierarchy_factory("""
        1
        2
            2.1
            2.2
        3
            3.1
            3.2
            3.3
    """)


def update_org_hierarchy(goal_string: str):
    # Only handles moving subtrees around for now
    uuid_for_name: dict[str, str | None] = {'<dummy>': None}
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
                node_data[field] = goal_uuid_str or None
            serializer_input.append(node_data)
    serializer = OrganizationSerializer(many=True, data=serializer_input, instance=Organization.objects.all())
    assert serializer.is_valid()
    serializer.save()


def test_organization_bulk_serializer_move_org1_after_org2(original_org_hierarchy):
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


def test_organization_bulk_serializer_move_org1_after_org21(original_org_hierarchy):
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


def test_organization_bulk_serializer_move_org22_after_org3(original_org_hierarchy):
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


def test_organization_bulk_serializer_move_org3_below_org22(original_org_hierarchy):
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
def test_organization_bulk_serializer_move_children_of_org3(original_org_hierarchy, order):
    expected = f"""
        1
        2
            2.1
            2.2
        3
            3.{order[0] + 1}
            3.{order[1] + 1}
            3.{order[2] + 1}
    """
    update_org_hierarchy(expected)
    assert_org_hierarchy(expected)


@pytest.mark.parametrize('order', permutations(range(3)))
def test_organization_bulk_serializer_move_roots(original_org_hierarchy, order):
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
