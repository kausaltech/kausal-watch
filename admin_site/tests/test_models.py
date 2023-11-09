import pytest
from django.contrib.auth.models import AnonymousUser

from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin
from actions.models import ActionContactPerson
from actions.tests.factories import ActionContactFactory
from admin_site.tests.factories import BuiltInFieldCustomizationFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    'built_in_field_customization__instances_editable_by,'
    'expect_unprivileged,expect_editor,expect_moderator,expect_admin', [
        (InstancesEditableByMixin.EditableBy.AUTHENTICATED, True, True, True, True),
        (InstancesEditableByMixin.EditableBy.CONTACT_PERSONS, False, True, True, True),
        (InstancesEditableByMixin.EditableBy.MODERATORS, False, False, True, True),
        (InstancesEditableByMixin.EditableBy.PLAN_ADMINS, False, False, False, True),
        (InstancesEditableByMixin.EditableBy.NOT_EDITABLE, False, False, False, False),
    ]
)
def test_built_in_field_customization_is_action_field_editable_by(
    expect_unprivileged, expect_editor, expect_moderator, expect_admin, built_in_field_customization, action,
    plan_admin_user
):
    unauthenticated = AnonymousUser()
    # Create an authenticated user that's unprivileged for this action because they are a contact for another action
    unprivileged = ActionContactFactory().person.user
    editor = ActionContactFactory(action=action, role=ActionContactPerson.Role.EDITOR).person.user
    moderator = ActionContactFactory(action=action, role=ActionContactPerson.Role.MODERATOR).person.user
    assert not built_in_field_customization.is_instance_editable_by(unauthenticated, action.plan, action)
    assert built_in_field_customization.is_instance_editable_by(unprivileged, action.plan, action) == expect_unprivileged
    assert built_in_field_customization.is_instance_editable_by(editor, action.plan, action) == expect_editor
    assert built_in_field_customization.is_instance_editable_by(moderator, action.plan, action) == expect_moderator
    assert built_in_field_customization.is_instance_editable_by(plan_admin_user, action.plan, action) == expect_admin


@pytest.mark.parametrize(
    'built_in_field_customization__instances_visible_for,'
    'expect_unauthenticated,expect_unprivileged,expect_editor,expect_moderator,expect_admin', [
        # TODO: Also test visibility via GraphQL API somewhere
        (InstancesVisibleForMixin.VisibleFor.PUBLIC, True, True, True, True, True),
        (InstancesVisibleForMixin.VisibleFor.AUTHENTICATED, False, True, True, True, True),
        (InstancesVisibleForMixin.VisibleFor.CONTACT_PERSONS, False, False, True, True, True),
        (InstancesVisibleForMixin.VisibleFor.MODERATORS, False, False, False, True, True),
        (InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS, False, False, False, False, True),
    ]
)
def test_built_in_field_customization_is_action_field_visible_for(
    expect_unauthenticated, expect_unprivileged, expect_editor, expect_moderator, expect_admin,
    built_in_field_customization, action, plan_admin_user
):
    unauthenticated = AnonymousUser()
    # Create an authenticated user that's unprivileged for this action because they are a contact for another action
    unprivileged = ActionContactFactory().person.user
    editor = ActionContactFactory(action=action, role=ActionContactPerson.Role.EDITOR).person.user
    moderator = ActionContactFactory(action=action, role=ActionContactPerson.Role.MODERATOR).person.user
    assert built_in_field_customization.is_instance_visible_for(unauthenticated, action.plan, action) == expect_unauthenticated
    assert built_in_field_customization.is_instance_visible_for(unprivileged, action.plan, action) == expect_unprivileged
    assert built_in_field_customization.is_instance_visible_for(editor, action.plan, action) == expect_editor
    assert built_in_field_customization.is_instance_visible_for(moderator, action.plan, action) == expect_moderator
    assert built_in_field_customization.is_instance_visible_for(plan_admin_user, action.plan, action) == expect_admin


@pytest.mark.parametrize('editable_by', [
    InstancesEditableByMixin.EditableBy.AUTHENTICATED,
    InstancesEditableByMixin.EditableBy.CONTACT_PERSONS,
    InstancesEditableByMixin.EditableBy.MODERATORS,
    InstancesEditableByMixin.EditableBy.PLAN_ADMINS,
    InstancesEditableByMixin.EditableBy.NOT_EDITABLE,
])
def test_built_in_field_customization_accepts_any_editability(editable_by):
    BuiltInFieldCustomizationFactory(instances_editable_by=editable_by).full_clean()


@pytest.mark.parametrize('visible_for', [
    InstancesVisibleForMixin.VisibleFor.PUBLIC,
    InstancesVisibleForMixin.VisibleFor.AUTHENTICATED,
    InstancesVisibleForMixin.VisibleFor.CONTACT_PERSONS,
    InstancesVisibleForMixin.VisibleFor.MODERATORS,
    InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
])
def test_built_in_field_customization_accepts_any_visibility(visible_for):
    BuiltInFieldCustomizationFactory(instances_visible_for=visible_for).full_clean()
