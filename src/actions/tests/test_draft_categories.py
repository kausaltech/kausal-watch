"""Category changes in an action's draft stay in the draft until it is published."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from actions.models import Action
from actions.tests import action_admin_helpers as h
from actions.tests.factories import ActionFactory, CategoryFactory, CategoryTypeFactory, PlanFactory

if TYPE_CHECKING:
    from actions.models import Category, Plan

pytestmark = pytest.mark.django_db


def _live_categories(action: Action) -> list[str]:
    return list(Action.objects.get(pk=action.pk).categories.values_list('name', flat=True))


@pytest.fixture
def plan() -> Plan:
    return PlanFactory.create()


@pytest.fixture
def moderated_plan(plan: Plan) -> Plan:
    h.enable_moderation(plan)
    return plan


@pytest.fixture
def transport(plan: Plan) -> Category:
    theme = CategoryTypeFactory.create(
        plan=plan, name='Theme', identifier='theme', usable_for_actions=True, editable_for_actions=True
    )
    return CategoryFactory.create(type=theme, name='Transport')


def test_draft_with_a_category_change_leaves_the_live_action_alone(client, moderated_plan, transport):
    action = ActionFactory.create(plan=moderated_plan, name='Published name')

    h.post_edit(client, h.make_contact_person(action), action, name='Draft name', categories_theme=[transport.pk])

    live = Action.objects.get(pk=action.pk)
    assert live.name == 'Published name'
    assert _live_categories(action) == []
    draft = live.get_latest_revision_as_object()
    assert draft.name == 'Draft name'
    assert [category.name for category in draft.categories.all()] == ['Transport']


def test_publishing_the_draft_applies_its_categories(client, moderated_plan, transport):
    action = ActionFactory.create(plan=moderated_plan, name='Published name')
    h.post_edit(client, h.make_contact_person(action), action, name='Draft name', categories_theme=[transport.pk])

    h.post_edit(client, h.make_plan_admin(moderated_plan), action, 'publish')

    assert Action.objects.get(pk=action.pk).name == 'Draft name'
    assert _live_categories(action) == ['Transport']


def test_approving_the_draft_applies_its_categories(client, moderated_plan, transport):
    action = ActionFactory.create(plan=moderated_plan, name='Published name')
    h.post_edit(client, h.make_contact_person(action), action, 'submit', name='Draft name', categories_theme=[transport.pk])

    h.post_workflow_action(client, h.make_plan_admin(moderated_plan), action, 'approve')

    assert Action.objects.get(pk=action.pk).name == 'Draft name'
    assert _live_categories(action) == ['Transport']


def test_category_change_is_saved_at_once_without_moderation(client, plan, transport):
    action = ActionFactory.create(plan=plan)

    h.post_edit(client, h.make_contact_person(action), action, categories_theme=[transport.pk])

    assert _live_categories(action) == ['Transport']
