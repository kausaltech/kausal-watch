"""Tests for `Plan.get_all_related_plans`, which backs the plan switcher and the related plans block."""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db


def test_parent_with_several_related_plans_is_listed_once(plan_factory):
    """
    A plan reachable through the hierarchy is listed once, however it is linked.

    The relation is OR-ed together with a join over related_plans, so a plan
    holding more than one such link used to come back once per link.
    """
    other = plan_factory()
    parent = plan_factory()
    parent.related_plans.add(other)
    parent.related_plans.add(parent)
    child = plan_factory(parent=parent)

    assert list(child.get_all_related_plans()) == [parent]


def test_related_plans_includes_parent_and_siblings_once(plan_factory):
    parent = plan_factory()
    child = plan_factory(parent=parent)
    sibling = plan_factory(parent=parent)
    child.related_plans.add(parent, sibling)

    assert sorted(child.get_all_related_plans().values_list('pk', flat=True)) == sorted([parent.pk, sibling.pk])


def test_related_plans_excludes_self_even_when_linked_to_itself(plan_factory):
    """A plan related to itself is junk data, but it must not list itself."""
    plan = plan_factory()
    plan.related_plans.add(plan)

    assert list(plan.get_all_related_plans()) == []


def test_related_plans_inclusive_lists_self_once(plan_factory):
    plan = plan_factory()
    other = plan_factory()
    plan.related_plans.add(other, plan)

    assert sorted(plan.get_all_related_plans(inclusive=True).values_list('pk', flat=True)) == sorted([plan.pk, other.pk])


def test_parent_linked_to_two_other_plans_is_listed_once(plan_factory):
    """
    No stray data needed: two ordinary links on the parent are enough.

    The parent is reached through the hierarchy, and the join over
    related_plans yields one row per link it holds, so it used to be listed
    once per link even though none of those links point at this plan.
    """
    parent = plan_factory()
    parent.related_plans.add(plan_factory())
    parent.related_plans.add(plan_factory())
    child = plan_factory(parent=parent)

    assert list(child.get_all_related_plans()) == [parent]


def test_sibling_linked_to_two_other_plans_is_listed_once(plan_factory):
    parent = plan_factory()
    sibling = plan_factory(parent=parent)
    sibling.related_plans.add(plan_factory())
    sibling.related_plans.add(plan_factory())
    child = plan_factory(parent=parent)

    assert list(child.get_all_related_plans().filter(pk=sibling.pk)) == [sibling]


def test_child_linked_to_two_other_plans_is_listed_once(plan_factory):
    parent = plan_factory()
    child = plan_factory(parent=parent)
    child.related_plans.add(plan_factory())
    child.related_plans.add(plan_factory())

    assert list(parent.get_all_related_plans()) == [child]
