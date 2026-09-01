from __future__ import annotations

import typing

import pytest

from aplans.tests.tree import parse_tree_string

if typing.TYPE_CHECKING:
    from orgs.models import Organization

from .utils import tree_to_org


@pytest.fixture
def organization_hierarchy_factory():
    def _organization_hierachy_factory(tree_string: str) -> list[Organization]:
        trees = parse_tree_string(tree_string)
        return [tree_to_org(tree) for tree in trees]

    return _organization_hierachy_factory
