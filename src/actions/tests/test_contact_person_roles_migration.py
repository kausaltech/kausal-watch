"""The migration that switches on contact person roles in plans that rely on them for moderation."""

from __future__ import annotations

import importlib

from django.apps import apps
from django.contrib.contenttypes.models import ContentType

import pytest

from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin

from actions.models import Action, ActionContactPerson, Plan
from actions.tests.factories import (
    ActionContactFactory,
    ActionFactory,
    AttributeTypeFactory,
    PlanFactory,
    WorkflowFactory,
)
from admin_site.tests.factories import BuiltInFieldCustomizationFactory

pytestmark = pytest.mark.django_db

# The module name starts with a digit, so it cannot be imported by name.
enable_roles_where_in_use = importlib.import_module(
    'actions.migrations.0208_enable_contact_person_roles_where_in_use'
).enable_roles_where_in_use


def _plan(*, has_workflow: bool, contact_role: ActionContactPerson.Role) -> Plan:
    plan = PlanFactory.create()
    plan.features.has_action_contact_person_roles = False
    plan.features.moderation_workflow = WorkflowFactory.create() if has_workflow else None
    plan.features.save()
    ActionContactFactory.create(action=ActionFactory.create(plan=plan), role=contact_role)
    return plan


@pytest.mark.parametrize(
    ('has_workflow', 'contact_role', 'expected'),
    [
        (True, ActionContactPerson.Role.EDITOR, True),
        # Without editors, everyone may approve already, so hiding the roles changes nothing
        (True, ActionContactPerson.Role.MODERATOR, False),
        # Without moderation, the roles don't decide who may approve
        (False, ActionContactPerson.Role.EDITOR, False),
    ],
)
def test_roles_are_switched_on_where_editors_cannot_approve(has_workflow, contact_role, expected):
    plan = _plan(has_workflow=has_workflow, contact_role=contact_role)
    enable_roles_where_in_use(apps, None)
    plan.features.refresh_from_db()
    assert plan.features.has_action_contact_person_roles is expected


def test_roles_are_switched_on_where_an_editor_exists_only_in_a_draft():
    plan = _plan(has_workflow=True, contact_role=ActionContactPerson.Role.MODERATOR)
    action = plan.actions.get()
    contact = action.contact_persons.all()[0]
    contact.role = ActionContactPerson.Role.EDITOR
    # Change the draft through the cluster relation, so the revision picks it up
    action.contact_persons.set([contact])
    action.save_revision()
    # The live row stays a moderator; only the draft makes the person an editor
    assert ActionContactPerson.objects.get(pk=contact.pk).role == ActionContactPerson.Role.MODERATOR
    enable_roles_where_in_use(apps, None)
    plan.features.refresh_from_db()
    assert plan.features.has_action_contact_person_roles is True


def test_roles_are_switched_on_where_moderators_are_hidden_publicly():
    plan = _plan(has_workflow=False, contact_role=ActionContactPerson.Role.MODERATOR)
    plan.features.contact_persons_hide_moderators = True
    plan.features.save()
    enable_roles_where_in_use(apps, None)
    plan.features.refresh_from_db()
    assert plan.features.has_action_contact_person_roles is True


def _restrict_a_field_to_moderators(plan: Plan, kind: str) -> None:
    if kind == 'built-in field':
        BuiltInFieldCustomizationFactory.create(
            plan=plan, field_name='description', instances_visible_for=InstancesVisibleForMixin.VisibleFor.MODERATORS
        )
    else:
        AttributeTypeFactory.create(
            scope=plan,
            object_content_type=ContentType.objects.get_for_model(Action),
            instances_editable_by=InstancesEditableByMixin.EditableBy.MODERATORS,
        )


@pytest.mark.parametrize('kind', ['built-in field', 'attribute type'])
@pytest.mark.parametrize(
    ('contact_role', 'expected'),
    [
        (ActionContactPerson.Role.EDITOR, True),
        # Without editors, "moderators" means all contact persons, which is what the plan gets without roles too
        (ActionContactPerson.Role.MODERATOR, False),
    ],
)
def test_roles_are_switched_on_where_editors_are_kept_from_moderator_only_fields(kind, contact_role, expected):
    plan = _plan(has_workflow=False, contact_role=contact_role)
    _restrict_a_field_to_moderators(plan, kind)
    enable_roles_where_in_use(apps, None)
    plan.features.refresh_from_db()
    assert plan.features.has_action_contact_person_roles is expected
