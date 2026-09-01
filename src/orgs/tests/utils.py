from __future__ import annotations

from typing import TYPE_CHECKING

from aplans.tests.tree import Tree, parse_tree_string

from orgs.models import Organization

from .factories import OrganizationFactory

if TYPE_CHECKING:
    from collections.abc import Iterable


def tree_to_org(tree: Tree, parent: Organization | None = None):
    org = OrganizationFactory.create(name=tree.name, abbreviation=tree.name, parent=parent)
    for child in tree.children:
        tree_to_org(child, org)
    return org


def orgs_to_trees(roots: Iterable[Organization], indent=0):
    result: list[Tree] = []
    for root in roots:
        tree = Tree(root.name, indent)
        for child in orgs_to_trees(root.get_children(), indent + 4):
            tree.add_child(child)
        result.append(tree)
    return result


def assert_org_hierarchy(expected_hierarchy: str):
    actual_roots = Organization.get_root_nodes()
    actual = orgs_to_trees(actual_roots)
    expected = parse_tree_string(expected_hierarchy)
    # We could use this, but comparing the values as strings produces nicer error messages
    # assert len(actual) == len(expected)
    # assert all(a.equals(e) for (a, e) in zip(actual, expected))
    actual_str = ''.join(str(tree) for tree in actual)
    expected_str = ''.join(str(tree) for tree in expected)
    assert actual_str == expected_str, f'\n{actual_str}\n!=\n{expected_str}'
