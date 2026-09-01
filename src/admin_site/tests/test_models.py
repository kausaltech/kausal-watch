from django.contrib.auth.models import AnonymousUser

import pytest

from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin

from actions.models import Action, ActionContactPerson
from actions.tests.factories import ActionContactFactory
from admin_site.models import BuiltInFieldCustomization
from admin_site.tests.factories import BuiltInFieldCustomizationFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    (
        'built_in_field_customization__instances_editable_by',
        'expect_unprivileged',
        'expect_editor',
        'expect_moderator',
        'expect_admin',
    ),
    [
        (InstancesEditableByMixin.EditableBy.AUTHENTICATED, True, True, True, True),
        (InstancesEditableByMixin.EditableBy.CONTACT_PERSONS, False, True, True, True),
        (InstancesEditableByMixin.EditableBy.MODERATORS, False, False, True, True),
        (InstancesEditableByMixin.EditableBy.PLAN_ADMINS, False, False, False, True),
        (InstancesEditableByMixin.EditableBy.NOT_EDITABLE, False, False, False, False),
    ],
)
def test_built_in_field_customization_is_action_field_editable_by(
    expect_unprivileged,
    expect_editor,
    expect_moderator,
    expect_admin,
    built_in_field_customization,
    action,
    plan_admin_user,
):
    unauthenticated = AnonymousUser()
    # Create an authenticated user that's unprivileged for this action because they are a contact for another action
    unprivileged = ActionContactFactory.create().person.user
    editor = ActionContactFactory.create(action=action, role=ActionContactPerson.Role.EDITOR).person.user
    moderator = ActionContactFactory.create(action=action, role=ActionContactPerson.Role.MODERATOR).person.user
    assert not built_in_field_customization.is_instance_editable_by(unauthenticated, action.plan, action)
    assert built_in_field_customization.is_instance_editable_by(unprivileged, action.plan, action) == expect_unprivileged
    assert built_in_field_customization.is_instance_editable_by(editor, action.plan, action) == expect_editor
    assert built_in_field_customization.is_instance_editable_by(moderator, action.plan, action) == expect_moderator
    assert built_in_field_customization.is_instance_editable_by(plan_admin_user, action.plan, action) == expect_admin


@pytest.mark.parametrize(
    (
        'built_in_field_customization__instances_visible_for',
        'expect_unauthenticated',
        'expect_unprivileged',
        'expect_editor',
        'expect_moderator',
        'expect_admin',
    ),
    [
        # TODO: Also test visibility via GraphQL API somewhere
        (InstancesVisibleForMixin.VisibleFor.PUBLIC, True, True, True, True, True),
        (InstancesVisibleForMixin.VisibleFor.AUTHENTICATED, False, True, True, True, True),
        (InstancesVisibleForMixin.VisibleFor.CONTACT_PERSONS, False, False, True, True, True),
        (InstancesVisibleForMixin.VisibleFor.MODERATORS, False, False, False, True, True),
        (InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS, False, False, False, False, True),
    ],
)
def test_built_in_field_customization_is_action_field_visible_for(
    expect_unauthenticated,
    expect_unprivileged,
    expect_editor,
    expect_moderator,
    expect_admin,
    built_in_field_customization,
    action,
    plan_admin_user,
):
    unauthenticated = AnonymousUser()
    # Create an authenticated user that's unprivileged for this action because they are a contact for another action
    unprivileged = ActionContactFactory.create().person.user
    editor = ActionContactFactory.create(action=action, role=ActionContactPerson.Role.EDITOR).person.user
    moderator = ActionContactFactory.create(action=action, role=ActionContactPerson.Role.MODERATOR).person.user
    assert built_in_field_customization.is_instance_visible_for(unauthenticated, action.plan, action) == expect_unauthenticated
    assert built_in_field_customization.is_instance_visible_for(unprivileged, action.plan, action) == expect_unprivileged
    assert built_in_field_customization.is_instance_visible_for(editor, action.plan, action) == expect_editor
    assert built_in_field_customization.is_instance_visible_for(moderator, action.plan, action) == expect_moderator
    assert built_in_field_customization.is_instance_visible_for(plan_admin_user, action.plan, action) == expect_admin


@pytest.mark.parametrize(
    'editable_by',
    [
        InstancesEditableByMixin.EditableBy.AUTHENTICATED,
        InstancesEditableByMixin.EditableBy.CONTACT_PERSONS,
        InstancesEditableByMixin.EditableBy.MODERATORS,
        InstancesEditableByMixin.EditableBy.PLAN_ADMINS,
        InstancesEditableByMixin.EditableBy.NOT_EDITABLE,
    ],
)
def test_built_in_field_customization_accepts_any_editability(editable_by):
    BuiltInFieldCustomizationFactory.create(instances_editable_by=editable_by).full_clean()


@pytest.mark.parametrize(
    'visible_for',
    [
        InstancesVisibleForMixin.VisibleFor.PUBLIC,
        InstancesVisibleForMixin.VisibleFor.AUTHENTICATED,
        InstancesVisibleForMixin.VisibleFor.CONTACT_PERSONS,
        InstancesVisibleForMixin.VisibleFor.MODERATORS,
        InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
    ],
)
def test_built_in_field_customization_accepts_any_visibility(visible_for):
    BuiltInFieldCustomizationFactory.create(instances_visible_for=visible_for).full_clean()


def test_get_field_access_without_customization(action, plan_admin_user):
    assert BuiltInFieldCustomization.get_field_access(plan_admin_user, action.plan, Action, 'tasks', action) == (
        True,
        True,
    )


def test_get_field_access_returns_raw_visibility_and_editability(action, plan_admin_user):
    contact_person = ActionContactFactory.create(action=action).person
    contact_user = contact_person.user
    assert contact_user is not None
    BuiltInFieldCustomizationFactory.create(
        plan=action.plan,
        field_name='tasks',
        instances_visible_for=InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
        instances_editable_by=InstancesEditableByMixin.EditableBy.AUTHENTICATED,
    )
    # Editability must not be allowed to imply visibility; the caller decides that.
    assert BuiltInFieldCustomization.get_field_access(contact_user, action.plan, Action, 'tasks', action) == (False, True)
    assert BuiltInFieldCustomization.get_field_access(plan_admin_user, action.plan, Action, 'tasks', action) == (
        True,
        True,
    )


def test_get_field_access_uses_field_name_and_model(action, plan_admin_user):
    BuiltInFieldCustomizationFactory.create(
        plan=action.plan,
        field_name='tasks',
        instances_visible_for=InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
        instances_editable_by=InstancesEditableByMixin.EditableBy.NOT_EDITABLE,
    )
    # A customization for another field must not affect this one
    assert BuiltInFieldCustomization.get_field_access(plan_admin_user, action.plan, Action, 'links', action) == (
        True,
        True,
    )
