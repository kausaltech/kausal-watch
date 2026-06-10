"""
Tests for AttributeTypeChoiceOption deletion scenarios.

These tests verify that deleting AttributeTypeChoiceOption instances is handled
gracefully across different contexts:
- Direct database references (AttributeChoice, AttributeChoiceWithText)
- Draft attributes in Wagtail revisions (moderation workflow)
- Report snapshots via django-reversion
- GraphQL API queries
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import reversion
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

import pytest

from actions.attributes import (
    AttributeType as AttributeTypeWrapper,
    DraftAttributes,
    OptionalChoiceWithTextAttributeValue,
    OrderedChoiceAttributeValue,
)
from actions.models import (
    Action,
    AttributeChoice,
    AttributeChoiceWithText,
    AttributeType,
    AttributeTypeChoiceOption,
)
from actions.tests.factories import (
    ActionFactory,
    AttributeChoiceFactory,
    AttributeChoiceWithTextFactory,
    AttributeTypeChoiceOptionFactory,
    AttributeTypeFactory,
)
from reports.models import ActionSnapshot
from reports.tests.factories import ReportFactory, ReportTypeFactory

if TYPE_CHECKING:
    from actions.models.category import Category, CategoryType
    from actions.models.plan import Plan
    from users.models import User

pytestmark = pytest.mark.django_db


# =============================================================================
# Helper Functions
# =============================================================================


def get_action_content_type():
    """Get the ContentType for Action model."""
    return ContentType.objects.get_for_model(Action)


def count_choice_attributes_for_action(action: Action) -> int:
    """Count AttributeChoice instances for an action using proper filtering."""
    ct = get_action_content_type()
    return AttributeChoice.objects.filter(content_type=ct, object_id=action.pk).count()


def count_choice_with_text_attributes_for_action(action: Action) -> int:
    """Count AttributeChoiceWithText instances for an action using proper filtering."""
    ct = get_action_content_type()
    return AttributeChoiceWithText.objects.filter(content_type=ct, object_id=action.pk).count()


# =============================================================================
# Fixtures
# =============================================================================

# The following registered fixtures from conftest.py are used throughout:
#   - action_attribute_type__ordered_choice (AttributeType)
#   - action_attribute_type__optional_choice (AttributeType, format=OPTIONAL_CHOICE_WITH_TEXT)
#   - attribute_type_choice_option (AttributeTypeChoiceOption for ordered_choice)
#   - attribute_type_choice_option__optional (AttributeTypeChoiceOption for optional_choice)


@pytest.fixture
def action_with_choice_attribute(
    plan: Plan,
    attribute_type_choice_option: AttributeTypeChoiceOption,
) -> Action:
    """Create an action with a choice attribute."""
    action = ActionFactory.create(plan=plan)
    AttributeChoiceFactory.create(
        type=attribute_type_choice_option.type,
        content_object=action,
        choice=attribute_type_choice_option,
    )
    return action


@pytest.fixture
def action_with_choice_with_text_attribute(
    plan: Plan,
    attribute_type_choice_option__optional: AttributeTypeChoiceOption,
) -> Action:
    """Create an action with a choice-with-text attribute."""
    action = ActionFactory.create(plan=plan)
    AttributeChoiceWithTextFactory.create(
        type=attribute_type_choice_option__optional.type,
        content_object=action,
        choice=attribute_type_choice_option__optional,
        text='Some explanatory text',
    )
    return action


# =============================================================================
# 1. Basic Deletion Cascade Behavior
# =============================================================================


class TestBasicDeletionCascade:
    """Tests for basic CASCADE behavior when deleting AttributeTypeChoiceOption."""

    def test_deleting_choice_option_cascades_to_attribute_choice(
        self,
        action_with_choice_attribute: Action,
        attribute_type_choice_option: AttributeTypeChoiceOption,
    ):
        """Deleting a choice option should cascade-delete related AttributeChoice instances."""
        action = action_with_choice_attribute

        # Verify the attribute exists
        assert count_choice_attributes_for_action(action) == 1

        # Delete the choice option
        attribute_type_choice_option.delete()

        # Verify the AttributeChoice was also deleted (CASCADE)
        assert count_choice_attributes_for_action(action) == 0

    def test_deleting_choice_option_cascades_to_attribute_choice_with_text(
        self,
        action_with_choice_with_text_attribute: Action,
        attribute_type_choice_option__optional: AttributeTypeChoiceOption,
    ):
        """Deleting a choice option should cascade-delete related AttributeChoiceWithText instances."""
        action = action_with_choice_with_text_attribute

        # Verify the attribute exists
        assert count_choice_with_text_attributes_for_action(action) == 1

        # Delete the choice option
        attribute_type_choice_option__optional.delete()

        # Verify the AttributeChoiceWithText was also deleted (CASCADE)
        # Note: The FK is nullable but uses CASCADE, so the whole record is deleted
        assert count_choice_with_text_attributes_for_action(action) == 0

    def test_deleting_option_used_by_multiple_actions(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """Deleting a choice option used by multiple actions should cascade to all."""
        # Create a single choice option
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Shared Option',
        )

        # Create multiple actions using this option
        actions = []
        for _ in range(3):
            action = ActionFactory.create(plan=plan)
            AttributeChoiceFactory.create(
                type=action_attribute_type__ordered_choice,
                content_object=action,
                choice=option,
            )
            actions.append(action)

        # Verify all attributes exist
        assert AttributeChoice.objects.filter(choice=option).count() == 3

        # Delete the option
        option.delete()

        # Verify all AttributeChoice instances were deleted
        for action in actions:
            assert count_choice_attributes_for_action(action) == 0

    def test_deleting_all_options_from_attribute_type(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """Deleting all options from an attribute type should cascade to all related attributes."""
        # Create multiple options
        options = [
            AttributeTypeChoiceOptionFactory.create(
                type=action_attribute_type__ordered_choice,
                name=f'Option {i}',
            )
            for i in range(3)
        ]

        # Create actions with different options
        for option in options:
            action = ActionFactory.create(plan=plan)
            AttributeChoiceFactory.create(
                type=action_attribute_type__ordered_choice,
                content_object=action,
                choice=option,
            )

        # Verify attributes exist
        assert AttributeChoice.objects.filter(type=action_attribute_type__ordered_choice).count() == 3

        # Delete all options
        for option in options:
            option.delete()

        # Verify all attributes were deleted
        assert AttributeChoice.objects.filter(type=action_attribute_type__ordered_choice).count() == 0


# =============================================================================
# 2. Draft Attributes (Moderation Workflow)
# =============================================================================


class TestDraftAttributesDeletion:
    """Tests for handling deleted choice options in draft attributes."""

    def test_deserializing_draft_with_deleted_choice_option_sets_value_to_none(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """Deserializing a draft with a deleted choice option should set value to None gracefully."""
        # Create a choice option
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Soon to be deleted',
        )
        option_pk = option.pk

        # Simulate serialized draft data with this option
        serialized_data = {
            'ordered_choice': {
                str(action_attribute_type__ordered_choice.pk): option_pk,
            }
        }

        # Delete the option
        option.delete()

        # Deserialize the draft - should not crash, should set option to None
        draft_attributes = DraftAttributes.from_revision_content(serialized_data)

        # Get the value - should have option=None
        attr_type_wrapper: AttributeTypeWrapper = AttributeTypeWrapper.from_model_instance(action_attribute_type__ordered_choice)
        value = draft_attributes.get_value_for_attribute_type(attr_type_wrapper)

        assert isinstance(value, OrderedChoiceAttributeValue)
        assert value.option is None

    def test_deserializing_draft_with_deleted_choice_in_optional_choice_with_text(
        self,
        action_attribute_type__optional_choice: AttributeType,
    ):
        """Deserializing an optional choice with text draft should preserve text when choice is deleted."""
        # Create a choice option
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__optional_choice,
            name='Soon to be deleted',
        )
        option_pk = option.pk

        # Simulate serialized draft data with this option and text
        serialized_data = {
            'optional_choice': {
                str(action_attribute_type__optional_choice.pk): {
                    'choice': option_pk,
                    'text': {'text': 'Important text that should be preserved'},
                },
            }
        }

        # Delete the option
        option.delete()

        # Deserialize the draft - should not crash
        draft_attributes = DraftAttributes.from_revision_content(serialized_data)

        # Get the value - choice should be None, text should be preserved
        attr_type_wrapper: AttributeTypeWrapper = AttributeTypeWrapper.from_model_instance(action_attribute_type__optional_choice)
        value = draft_attributes.get_value_for_attribute_type(attr_type_wrapper)

        assert isinstance(value, OptionalChoiceWithTextAttributeValue)
        assert value.option is None
        assert value.text_vals['text'] == 'Important text that should be preserved'

    def test_committing_draft_with_deleted_choice_option(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """Committing a draft with a deleted choice option should not create an attribute."""
        action = ActionFactory.create(plan=plan)

        # Create a choice option
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Soon to be deleted',
        )
        option_pk = option.pk

        # Simulate serialized draft data
        serialized_data = {
            'ordered_choice': {
                str(action_attribute_type__ordered_choice.pk): option_pk,
            }
        }

        # Delete the option
        option.delete()

        # Deserialize and commit the draft
        draft_attributes = DraftAttributes.from_revision_content(serialized_data)

        attr_type_wrapper: AttributeTypeWrapper = AttributeTypeWrapper.from_model_instance(action_attribute_type__ordered_choice)
        value = draft_attributes.get_value_for_attribute_type(attr_type_wrapper)

        # Commit should not create an attribute since option is None
        attr_type_wrapper.commit_attribute(action, value)

        # Verify no attribute was created
        assert count_choice_attributes_for_action(action) == 0

    def test_draft_attributes_serialization_roundtrip_with_deleted_option(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """Test that draft attributes can be serialized, option deleted, then deserialized."""
        # Create a choice option
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Roundtrip option',
        )

        # Create draft attributes with this option
        attr_type_wrapper: AttributeTypeWrapper = AttributeTypeWrapper.from_model_instance(action_attribute_type__ordered_choice)

        draft_attributes = DraftAttributes()
        draft_attributes.update(attr_type_wrapper, OrderedChoiceAttributeValue(option=option))

        # Serialize
        serialized = draft_attributes.get_serialized_data()

        # Delete the option
        option.delete()

        # Deserialize - should handle missing option
        restored = DraftAttributes.from_revision_content(serialized)
        value = restored.get_value_for_attribute_type(attr_type_wrapper)

        assert isinstance(value, OrderedChoiceAttributeValue)
        assert value.option is None


class TestDeserializationWarnings:
    """Tests for deserialization warnings when draft attributes reference deleted objects."""

    def test_warning_generated_for_deleted_choice_option(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """Deserializing a draft with a deleted choice option should generate a warning."""
        # Create a choice option
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Warning option',
        )
        option_pk = option.pk

        # Simulate serialized draft data with this option
        serialized_data = {
            'ordered_choice': {
                str(action_attribute_type__ordered_choice.pk): option_pk,
            }
        }

        # Delete the option
        option.delete()

        # Deserialize the draft
        draft_attributes = DraftAttributes.from_revision_content(serialized_data)

        # Verify a warning was generated
        assert len(draft_attributes.deserialization_warnings) == 1
        warning = draft_attributes.deserialization_warnings[0]
        assert warning.attribute_type_id == action_attribute_type__ordered_choice.pk
        assert warning.attribute_type_name == str(action_attribute_type__ordered_choice)
        assert 'choice option' in warning.message.lower()

    def test_warning_generated_for_deleted_optional_choice_with_text(
        self,
        action_attribute_type__optional_choice: AttributeType,
    ):
        """Deserializing optional choice with text with deleted option should generate a warning."""
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__optional_choice,
            name='Warning option with text',
        )
        option_pk = option.pk

        serialized_data = {
            'optional_choice': {
                str(action_attribute_type__optional_choice.pk): {
                    'choice': option_pk,
                    'text': {'text': 'Some text'},
                },
            }
        }

        option.delete()

        draft_attributes = DraftAttributes.from_revision_content(serialized_data)

        assert len(draft_attributes.deserialization_warnings) == 1
        warning = draft_attributes.deserialization_warnings[0]
        assert warning.attribute_type_id == action_attribute_type__optional_choice.pk
        assert 'choice option' in warning.message.lower()

    def test_warning_generated_for_deleted_attribute_type(
        self,
        plan: Plan,
    ):
        """Deserializing a draft with a deleted attribute type should generate a warning."""
        # Create an attribute type
        attr_type = AttributeTypeFactory.create(
            object_content_type=ContentType.objects.get_for_model(Action),
            scope=plan,
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
            name='Temporary Type',
        )
        attr_type_pk = attr_type.pk

        # Create a choice option
        option = AttributeTypeChoiceOptionFactory.create(
            type=attr_type,
            name='Option for temp type',
        )
        option_pk = option.pk

        # Simulate serialized draft data
        serialized_data = {
            'ordered_choice': {
                str(attr_type_pk): option_pk,
            }
        }

        # Delete the attribute type (cascades to option)
        attr_type.delete()

        # Deserialize the draft
        draft_attributes = DraftAttributes.from_revision_content(serialized_data)

        # Verify a warning was generated for the deleted attribute type
        assert len(draft_attributes.deserialization_warnings) == 1
        warning = draft_attributes.deserialization_warnings[0]
        assert warning.attribute_type_id == attr_type_pk
        assert warning.attribute_type_name is None  # Type doesn't exist, so no name
        assert 'field' in warning.message.lower()

    def test_no_warning_when_option_exists(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """No warning should be generated when choice option exists."""
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Existing option',
        )

        serialized_data = {
            'ordered_choice': {
                str(action_attribute_type__ordered_choice.pk): option.pk,
            }
        }

        # Don't delete the option

        draft_attributes = DraftAttributes.from_revision_content(serialized_data)

        # No warnings should be generated
        assert len(draft_attributes.deserialization_warnings) == 0

    def test_multiple_warnings_for_multiple_deleted_options(
        self,
        plan: Plan,
    ):
        """Multiple warnings should be generated when multiple attribute types have missing options."""
        attr_type1 = AttributeTypeFactory.create(
            object_content_type=ContentType.objects.get_for_model(Action),
            scope=plan,
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
            name='Type 1',
        )
        attr_type2 = AttributeTypeFactory.create(
            object_content_type=ContentType.objects.get_for_model(Action),
            scope=plan,
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
            name='Type 2',
        )

        option1 = AttributeTypeChoiceOptionFactory.create(type=attr_type1, name='Option 1')
        option2 = AttributeTypeChoiceOptionFactory.create(type=attr_type2, name='Option 2')

        serialized_data = {
            'ordered_choice': {
                str(attr_type1.pk): option1.pk,
                str(attr_type2.pk): option2.pk,
            }
        }

        # Delete both options
        option1.delete()
        option2.delete()

        draft_attributes = DraftAttributes.from_revision_content(serialized_data)

        # Two warnings should be generated
        assert len(draft_attributes.deserialization_warnings) == 2


# =============================================================================
# 3. Reports with Deleted Choice Options
# =============================================================================


class TestReportsDeletion:
    """Tests for handling deleted choice options in report snapshots."""

    def test_attribute_choice_str_handles_deleted_choice_option(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """AttributeChoice.__str__ should handle deleted choice option gracefully."""
        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Will be deleted',
        )

        # Create attribute
        attr = AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )

        # Verify str works before deletion
        assert str(attr) == 'Will be deleted'

        # Note: We cannot test this directly after deletion because CASCADE will
        # delete the AttributeChoice. This test documents the current behavior.
        # The __str__ method has special handling for ObjectDoesNotExist which
        # is used when deserializing old snapshots.

    def test_report_snapshot_with_deleted_choice_option(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
        user: User,
    ):
        """Creating a snapshot and then deleting the choice option should be handled gracefully."""
        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Snapshot option',
        )

        # Create attribute
        AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )

        # Create report type and report
        report_type = ReportTypeFactory.create(plan=plan)
        report = ReportFactory.create(type=report_type, is_complete=False)

        # Create a snapshot via marking complete
        with reversion.create_revision():
            reversion.set_user(user)
            reversion.add_to_revision(action)

        snapshot = ActionSnapshot.for_action(report=report, action=action)
        snapshot.save()

        # Get the attribute from snapshot before deletion
        attr_from_snapshot = snapshot.get_attribute_for_type(action_attribute_type__ordered_choice)
        assert attr_from_snapshot is not None
        # Access the choice_id via field_dict pattern
        assert attr_from_snapshot.choice_id == option.pk  # type: ignore[attr-defined]

        # Now delete the option (this cascades to the live AttributeChoice)
        option.delete()

        # The snapshot should still have the reference, but accessing .choice will fail
        # This simulates what happens with stale snapshot data
        attr_from_snapshot_after = snapshot.get_attribute_for_type(action_attribute_type__ordered_choice)
        # The attribute from snapshot still exists with the old choice_id
        assert attr_from_snapshot_after is not None
        # But calling str() should handle the missing choice gracefully
        # (returns "Missing value" and logs to Sentry)
        result = str(attr_from_snapshot_after)
        assert result == 'Missing value'

    def test_report_get_live_versions_with_deleted_choice(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """get_live_versions should not crash when choice options have been deleted."""
        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Live version option',
        )

        # Create attribute
        AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )

        # Create incomplete report
        report_type = ReportTypeFactory.create(plan=plan)
        report = ReportFactory.create(type=report_type, is_complete=False)

        # Delete the option (cascades to AttributeChoice)
        option.delete()

        # get_live_versions should still work
        live_versions = report.get_live_versions()

        # Should have one action version
        assert len(live_versions.actions) == 1

    def test_complete_report_undo_after_choice_deletion(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
        user: User,
    ):
        """Undoing report completion after choice option deletion should work."""
        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Report option',
        )

        # Create attribute
        AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )

        # Create and complete report
        report_type = ReportTypeFactory.create(plan=plan)
        report = ReportFactory.create(type=report_type, is_complete=False)
        report.mark_as_complete(user)

        assert report.is_complete
        assert report.action_snapshots.count() == 1

        # Delete the option
        option.delete()

        # Undo completion should still work
        report.undo_marking_as_complete(user)

        assert not report.is_complete


# =============================================================================
# 4. GraphQL API
# =============================================================================


class TestGraphQLDeletion:
    """Tests for GraphQL API behavior after choice option deletion."""

    def test_query_action_attributes_after_choice_deletion(
        self,
        graphql_client_query_data,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """Querying action attributes after choice option deletion should return empty list."""
        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='GraphQL option',
        )

        # Create attribute
        AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )

        # Verify attribute is returned before deletion
        data = graphql_client_query_data(
            """
            query($action: ID!) {
                action(id: $action) {
                    attributes {
                        ... on AttributeChoice {
                            id
                            choice {
                                name
                            }
                        }
                    }
                }
            }
            """,
            variables={'action': action.pk},
        )

        assert len(data['action']['attributes']) == 1
        assert data['action']['attributes'][0]['choice']['name'] == 'GraphQL option'

        # Delete the option (cascades to AttributeChoice)
        option.delete()

        # Query again - should return empty list
        data = graphql_client_query_data(
            """
            query($action: ID!) {
                action(id: $action) {
                    attributes {
                        ... on AttributeChoice {
                            id
                        }
                    }
                }
            }
            """,
            variables={'action': action.pk},
        )

        assert data['action']['attributes'] == []

    def test_query_attribute_type_choice_options_after_deletion(
        self,
        graphql_client_query_data,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """Querying attribute type choice options after deletion should return remaining options."""
        # Create multiple options
        option1 = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Option 1',
        )
        AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Option 2',
        )

        # Delete first option
        option1.delete()

        # Query attribute type - should only show remaining option
        data = graphql_client_query_data(
            """
            query($plan: ID!) {
                plan(id: $plan) {
                    actionAttributeTypes {
                        name
                        choiceOptions {
                            name
                        }
                    }
                }
            }
            """,
            variables={'plan': plan.identifier},
        )

        # Find our attribute type
        attr_type_data = next(
            at for at in data['plan']['actionAttributeTypes'] if at['name'] == action_attribute_type__ordered_choice.name
        )

        assert len(attr_type_data['choiceOptions']) == 1
        assert attr_type_data['choiceOptions'][0]['name'] == 'Option 2'


# =============================================================================
# 5. Edge Cases
# =============================================================================


class TestEdgeCases:
    """Tests for edge cases in choice option deletion."""

    def test_recreating_option_with_same_identifier_after_deletion(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        """Re-creating an option with the same identifier should not affect old draft references."""
        # Create and delete option
        old_option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Reused Name',
        )
        old_pk = old_option.pk

        # Simulate serialized draft with old option PK
        serialized_data = {
            'ordered_choice': {
                str(action_attribute_type__ordered_choice.pk): old_pk,
            }
        }

        # Delete the option
        old_option.delete()

        # Create new option with same name (will get different PK)
        new_option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Reused Name',
        )

        # New option should have different PK
        assert new_option.pk != old_pk

        # Deserializing old draft should get None, not the new option
        draft_attributes = DraftAttributes.from_revision_content(serialized_data)

        attr_type_wrapper: AttributeTypeWrapper = AttributeTypeWrapper.from_model_instance(action_attribute_type__ordered_choice)
        value = draft_attributes.get_value_for_attribute_type(attr_type_wrapper)

        assert isinstance(value, OrderedChoiceAttributeValue)
        assert value.option is None  # Should not resolve to the new option

    def test_deleting_attribute_type_cascades_to_options_and_attributes(
        self,
        plan: Plan,
    ):
        """Deleting an attribute type should cascade to options and attributes."""
        attr_type = AttributeTypeFactory.create(
            object_content_type=ContentType.objects.get_for_model(Action),
            scope=plan,
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
            name='Deletable Type',
        )

        option = AttributeTypeChoiceOptionFactory.create(
            type=attr_type,
            name='Deletable Option',
        )

        action = ActionFactory.create(plan=plan)
        AttributeChoiceFactory.create(
            type=attr_type,
            content_object=action,
            choice=option,
        )

        # Verify everything exists
        assert AttributeTypeChoiceOption.objects.filter(type=attr_type).count() == 1
        assert AttributeChoice.objects.filter(type=attr_type).count() == 1

        # Delete the attribute type
        attr_type.delete()

        # Everything should be deleted
        assert AttributeTypeChoiceOption.objects.filter(pk=option.pk).count() == 0
        assert count_choice_attributes_for_action(action) == 0

    def test_draft_with_multiple_deleted_choice_options(
        self,
        plan: Plan,
    ):
        """Draft with multiple different attribute types having deleted options should deserialize."""
        # Create two attribute types
        attr_type1 = AttributeTypeFactory.create(
            object_content_type=ContentType.objects.get_for_model(Action),
            scope=plan,
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
            name='Type 1',
        )
        attr_type2 = AttributeTypeFactory.create(
            object_content_type=ContentType.objects.get_for_model(Action),
            scope=plan,
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
            name='Type 2',
        )

        option1 = AttributeTypeChoiceOptionFactory.create(type=attr_type1, name='Option 1')
        option2 = AttributeTypeChoiceOptionFactory.create(type=attr_type2, name='Option 2')

        # Simulate draft with both options
        serialized_data = {
            'ordered_choice': {
                str(attr_type1.pk): option1.pk,
                str(attr_type2.pk): option2.pk,
            }
        }

        # Delete both options
        option1.delete()
        option2.delete()

        # Deserialize should work and both should be None
        draft_attributes = DraftAttributes.from_revision_content(serialized_data)

        wrapper1: AttributeTypeWrapper = AttributeTypeWrapper.from_model_instance(attr_type1)
        value1 = draft_attributes.get_value_for_attribute_type(wrapper1)
        assert isinstance(value1, OrderedChoiceAttributeValue)
        assert value1.option is None

        wrapper2: AttributeTypeWrapper = AttributeTypeWrapper.from_model_instance(attr_type2)
        value2 = draft_attributes.get_value_for_attribute_type(wrapper2)
        assert isinstance(value2, OrderedChoiceAttributeValue)
        assert value2.option is None


# =============================================================================
# 6. Category Attributes
# =============================================================================


class TestCategoryAttributeDeletion:
    """Tests for choice option deletion affecting category attributes."""

    def test_deleting_choice_option_cascades_to_category_attribute(
        self,
        category_type: CategoryType,
        category: Category,
    ):
        """Deleting a choice option should cascade to CategoryAttributeChoice."""
        from actions.models import Category

        attr_type = AttributeTypeFactory.create(
            scope=category_type,
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
            name='Category Choice',
        )

        option = AttributeTypeChoiceOptionFactory.create(
            type=attr_type,
            name='Category Option',
        )

        # Create attribute on category
        AttributeChoiceFactory.create(
            type=attr_type,
            content_object=category,
            choice=option,
        )

        # Verify attribute exists
        ct = ContentType.objects.get_for_model(Category)
        assert AttributeChoice.objects.filter(content_type=ct, object_id=category.pk).count() == 1

        # Delete option
        option.delete()

        # Attribute should be deleted
        assert AttributeChoice.objects.filter(content_type=ct, object_id=category.pk).count() == 0


# =============================================================================
# 6. Archive / Unarchive API
# =============================================================================


class TestArchiveApi:
    """Tests for AttributeTypeChoiceOption.archive()/unarchive() and is_referenced()."""

    def test_archive_flips_flag_and_moves_order_out_of_active_range(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        first = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='First',
        )
        second = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Second',
        )
        assert first.is_active
        assert second.is_active

        first.archive()
        first.refresh_from_db()

        assert first.is_active is False
        # Archive bumps the row above all siblings so the inline editor's
        # renumbering of active rows can't collide with it.
        second.refresh_from_db()
        assert first.order > second.order

    def test_archive_is_idempotent(
        self,
        attribute_type_choice_option: AttributeTypeChoiceOption,
    ):
        attribute_type_choice_option.archive()
        attribute_type_choice_option.refresh_from_db()
        order_after_first_archive = attribute_type_choice_option.order

        attribute_type_choice_option.archive()
        attribute_type_choice_option.refresh_from_db()

        assert attribute_type_choice_option.is_active is False
        assert attribute_type_choice_option.order == order_after_first_archive

    def test_unarchive_restores_active_flag(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        kept = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Active',
        )
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Cycles',
        )

        option.archive()
        option.refresh_from_db()
        assert option.is_active is False

        option.unarchive()
        option.refresh_from_db()
        kept.refresh_from_db()

        assert option.is_active is True
        # Unarchive places the option at the end of the order so it doesn't
        # collide with the inline editor's renumbering of other rows.
        assert option.order > kept.order

    def test_unarchive_is_idempotent(
        self,
        attribute_type_choice_option: AttributeTypeChoiceOption,
    ):
        original_order = attribute_type_choice_option.order
        attribute_type_choice_option.unarchive()
        attribute_type_choice_option.refresh_from_db()

        assert attribute_type_choice_option.is_active is True
        assert attribute_type_choice_option.order == original_order

    def test_new_option_does_not_collide_with_archived_order(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # Archiving a row keeps it in the (type, order) unique-constraint
        # picture. A newly created option must skip that slot.
        first = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='First',
        )
        first.archive()
        first.refresh_from_db()

        second = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Second',
        )

        assert second.order != first.order


# =============================================================================
# 7. Picker visibility of archived options
# =============================================================================


class TestPickerVisibility:
    """Editor pickers and GraphQL listings hide archived options."""

    def _picker_options(
        self,
        attribute_type: AttributeType,
        user: User,
        plan: Plan,
        obj: Action | None = None,
    ):
        wrapper: AttributeTypeWrapper = AttributeTypeWrapper.from_model_instance(attribute_type)
        fields = wrapper.get_all_form_fields(user=user, plan=plan, obj=obj)
        # The choice picker is the field whose django_field is a ModelChoiceField.
        from django.forms import ModelChoiceField

        choice_fields = [f for f in fields if isinstance(f.django_field, ModelChoiceField)]
        assert choice_fields, 'expected a ModelChoiceField in the form fields'
        django_field = cast('ModelChoiceField', choice_fields[0].django_field)
        assert django_field.queryset is not None
        return list(django_field.queryset)

    def test_ordered_choice_picker_excludes_archived_options(
        self,
        plan: Plan,
        user: User,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        kept = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Kept',
        )
        gone = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Gone',
        )
        gone.archive()

        options = self._picker_options(action_attribute_type__ordered_choice, user, plan)
        pks = {o.pk for o in options}

        assert kept.pk in pks
        assert gone.pk not in pks

    def test_picker_keeps_currently_selected_archived_option(
        self,
        plan: Plan,
        user: User,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        archived = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Stale value',
        )
        action = ActionFactory.create(plan=plan)
        AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=archived,
        )
        archived.archive()

        options = self._picker_options(
            action_attribute_type__ordered_choice,
            user,
            plan,
            obj=action,
        )
        pks = {o.pk for o in options}

        assert archived.pk in pks, 'archived option must remain selectable so the existing value is preserved'

    def test_optional_choice_with_text_picker_excludes_archived(
        self,
        plan: Plan,
        user: User,
        action_attribute_type__optional_choice: AttributeType,
    ):
        kept = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__optional_choice,
            name='Kept',
        )
        gone = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__optional_choice,
            name='Gone',
        )
        gone.archive()

        options = self._picker_options(action_attribute_type__optional_choice, user, plan)
        pks = {o.pk for o in options}

        assert kept.pk in pks
        assert gone.pk not in pks

    def test_graphql_choice_options_lists_archived_with_is_active_flag(
        self,
        graphql_client_query_data,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # GraphQL exposes archived options so REST consumers (e.g. the
        # spreadsheet table editor) can resolve labels for historical PKs.
        # Each option carries `isActive` so clients can filter when building
        # selection UIs.
        kept = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Kept',
        )
        gone = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Gone',
        )
        gone.archive()

        data = graphql_client_query_data(
            """
            query($plan: ID!) {
                plan(id: $plan) {
                    actionAttributeTypes {
                        name
                        choiceOptions {
                            name
                            isActive
                        }
                    }
                }
            }
            """,
            variables={'plan': plan.identifier},
        )

        attr_type_data = next(
            at for at in data['plan']['actionAttributeTypes'] if at['name'] == action_attribute_type__ordered_choice.name
        )

        by_name = {opt['name']: opt for opt in attr_type_data['choiceOptions']}
        assert by_name[kept.name]['isActive'] is True
        assert by_name[gone.name]['isActive'] is False

    def test_active_queryset_excludes_archived(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        kept = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Kept',
        )
        gone = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Gone',
        )
        gone.archive()

        active = set(
            AttributeTypeChoiceOption.objects
            .filter(type=action_attribute_type__ordered_choice)
            .active()
            .values_list('pk', flat=True),
        )
        archived = set(
            AttributeTypeChoiceOption.objects
            .filter(type=action_attribute_type__ordered_choice)
            .archived()
            .values_list('pk', flat=True),
        )
        assert active == {kept.pk}
        assert archived == {gone.pk}

    def test_is_referenced_when_live_attribute_choice_exists(
        self,
        action_with_choice_attribute: Action,
        attribute_type_choice_option: AttributeTypeChoiceOption,
    ):
        del action_with_choice_attribute  # the fixture creates the AttributeChoice
        assert attribute_type_choice_option.is_referenced() is True

    def test_is_referenced_when_live_attribute_choice_with_text_exists(
        self,
        action_with_choice_with_text_attribute: Action,
        attribute_type_choice_option__optional: AttributeTypeChoiceOption,
    ):
        del action_with_choice_with_text_attribute
        assert attribute_type_choice_option__optional.is_referenced() is True

    def test_is_referenced_when_wagtail_revision_references_option(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        import json

        from wagtail.models import Revision

        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Referenced in draft',
        )

        # Inject a Wagtail revision whose serialized content references this
        # option. `Revision.content` is a JSONField; the codebase stores it as
        # serialized text and matches against substrings of that text, so we
        # do the same here.
        Revision.objects.create(
            content_type=ContentType.objects.get_for_model(Action),
            base_content_type=ContentType.objects.get_for_model(Action),
            object_id=str(action.pk),
            content=json.loads(
                json.dumps({
                    'attributes': {
                        'ordered_choice': {
                            str(action_attribute_type__ordered_choice.pk): option.pk,
                        },
                    },
                })
            ),
        )

        assert option.is_referenced() is True

    def test_is_referenced_when_reversion_version_references_option(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
        user: User,
    ):
        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Referenced in reversion',
        )
        attr = AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )

        with reversion.create_revision():
            reversion.set_user(user)
            reversion.add_to_revision(attr)

        # Hard-delete the live attribute so we know the True comes from the
        # reversion Version row, not the live FK.
        attr.delete()
        assert not AttributeChoice.objects.filter(choice=option).exists()

        assert option.is_referenced() is True

    def test_is_referenced_returns_false_when_unused(
        self,
        attribute_type_choice_option: AttributeTypeChoiceOption,
    ):
        assert attribute_type_choice_option.is_referenced() is False

    def test_full_clean_rejects_new_attribute_with_archived_choice(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # Defense in depth: any save path that runs full_clean() — REST,
        # admin forms, anything that calls .clean() — must reject an
        # archived option being assigned as a new value.
        from django.core.exceptions import ValidationError as CoreValidationError

        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Archived',
        )
        option.archive()

        attr = AttributeChoice(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )
        with pytest.raises(CoreValidationError):
            attr.full_clean()

    def test_full_clean_allows_resaving_existing_archived_choice(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Once-active',
        )
        attr = AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )
        option.archive()

        # Re-saving the same archived option on the existing row must succeed
        # so admins can save unrelated edits without first picking a new option.
        attr.full_clean()

    def test_full_clean_rejects_switching_to_archived_choice(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        from django.core.exceptions import ValidationError as CoreValidationError

        action = ActionFactory.create(plan=plan)
        active = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Active',
        )
        archived = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Archived',
        )
        attr = AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=active,
        )
        archived.archive()

        attr.choice = archived
        with pytest.raises(CoreValidationError):
            attr.full_clean()

    def test_save_rejects_new_attribute_with_archived_choice(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # DRF and other paths bypass full_clean() and call .save() directly,
        # so the rule has to hold at save time too.
        from django.core.exceptions import ValidationError as CoreValidationError

        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Archived',
        )
        option.archive()

        attr = AttributeChoice(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )
        with pytest.raises(CoreValidationError):
            attr.save()
        action_ct = ContentType.objects.get_for_model(Action)
        assert (
            AttributeChoice.objects.filter(
                type=action_attribute_type__ordered_choice,
                content_type=action_ct,
                object_id=action.pk,
            ).count()
            == 0
        )

    def test_save_allows_resaving_existing_archived_choice(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Once-active',
        )
        attr = AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )
        option.archive()

        # No exception — in-place re-save of an unchanged archived value is OK.
        attr.save()

    def test_save_rejects_switching_to_archived_choice(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        from django.core.exceptions import ValidationError as CoreValidationError

        action = ActionFactory.create(plan=plan)
        active = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Active',
        )
        archived = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Archived',
        )
        attr = AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=active,
        )
        archived.archive()

        attr.choice = archived
        with pytest.raises(CoreValidationError):
            attr.save()
        attr.refresh_from_db()
        assert attr.choice_id == active.pk

    def test_set_attribute_rejects_archived_choice_for_rest_bulk_path(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # The REST bulk path queues operations through `set_attribute()` and
        # later applies them via QuerySet.bulk_update()/bulk_create(), which
        # bypass both save() and full_clean(). The guard at set_attribute()
        # rejects archived options before the op reaches the queue.
        from django.core.exceptions import ValidationError as CoreValidationError

        from actions.attributes import AttributeType as AttributeTypeWrapper

        action = ActionFactory.create(plan=plan)
        archived_opt = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Archived',
        )
        archived_opt.archive()

        wrapper: AttributeTypeWrapper = AttributeTypeWrapper.from_model_instance(
            action_attribute_type__ordered_choice,
        )

        with pytest.raises(CoreValidationError):
            action.set_attribute(
                attribute_type=wrapper,
                existing_attribute=None,
                value_parameters={'choice_id': archived_opt.pk},
                attribute_value_input=archived_opt.pk,
            )

    def test_set_attribute_allows_resaving_existing_archived_choice(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        from actions.attributes import AttributeType as AttributeTypeWrapper

        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Once-active',
        )
        existing = AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )
        option.archive()

        wrapper: AttributeTypeWrapper = AttributeTypeWrapper.from_model_instance(
            action_attribute_type__ordered_choice,
        )

        # Re-asserting the same archived option as the current value must pass —
        # this matches the picker's "keep selected archived value editable" UX.
        op = action.set_attribute(
            attribute_type=wrapper,
            existing_attribute=existing,
            value_parameters={'choice_id': option.pk},
            attribute_value_input=option.pk,
        )
        assert op[0] == 'update'

    def test_save_allows_archived_choice_referenced_in_parent_draft(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # The publish-from-draft path: a draft of this action selected the
        # option, the option was later archived (kept around solely because
        # is_referenced() found the draft), and publishing the draft now
        # creates a new AttributeChoice with the archived choice. The
        # model-layer validator must allow this — rejecting it would block
        # users from publishing drafts that pre-date the archive.
        from wagtail.models import Revision

        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Picked in draft, then archived',
        )
        Revision.objects.create(
            content_type=ContentType.objects.get_for_model(Action),
            base_content_type=ContentType.objects.get_for_model(Action),
            object_id=str(action.pk),
            content={
                'attributes': {
                    'ordered_choice': {
                        str(action_attribute_type__ordered_choice.pk): option.pk,
                    },
                },
            },
        )
        option.archive()

        # Materialise the choice from the draft — same path that
        # `Action.commit_attributes()` takes on publish.
        attr = AttributeChoice(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )
        attr.save()
        assert attr.pk is not None
        assert attr.choice_id == option.pk

    def test_save_still_rejects_archived_choice_without_draft_reference(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # Counterpart to the publish-from-draft case: when no revision of
        # this action references the choice, the model-layer guard still
        # rejects a fresh archived selection.
        from django.core.exceptions import ValidationError as CoreValidationError

        action = ActionFactory.create(plan=plan)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Archived without draft',
        )
        option.archive()

        attr = AttributeChoice(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )
        with pytest.raises(CoreValidationError):
            attr.save()

    def test_rest_bulk_update_rejects_archived_choice_before_save(
        self,
        api_client,
        plan: Plan,
        plan_admin_user,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # Reproduce the production bypass: a REST PUT to /v1/plan/<id>/actions/
        # carrying an archived choice option as a new assignment.
        # The validation must fire during is_valid(), before the (potentially
        # expensive) Action save runs — the response should be a 400 with no
        # AttributeChoice row written.
        action_ct = ContentType.objects.get_for_model(Action)
        action = ActionFactory.create(plan=plan)
        archived_opt = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Archived',
        )
        archived_opt.archive()

        api_client.force_login(plan_admin_user)
        url = reverse('action-list', args=(plan.pk,))
        payload = [
            {
                'id': action.pk,
                'identifier': action.identifier,
                'name': action.name,
                'choice_attributes': {
                    action_attribute_type__ordered_choice.identifier: archived_opt.pk,
                },
            },
        ]

        response = api_client.put(url, data=payload)

        assert response.status_code == 400, response.content
        assert (
            AttributeChoice.objects.filter(
                type=action_attribute_type__ordered_choice,
                content_type=action_ct,
                object_id=action.pk,
            ).count()
            == 0
        ), 'no AttributeChoice should be written'

    def test_rest_bulk_update_allows_resaving_existing_archived_choice(
        self,
        api_client,
        plan: Plan,
        plan_admin_user,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # The action already has this option as its current value, and the
        # option was later archived. A bulk PUT that re-submits the same
        # archived option (e.g. while editing unrelated fields) must NOT
        # be rejected — the value isn't changing, only being preserved.
        # Regression: the bulk path used to bail out of target-instance
        # resolution and lose track of the existing value entirely.
        action_ct = ContentType.objects.get_for_model(Action)
        action = ActionFactory.create(plan=plan)
        opt = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Stored then archived',
        )
        AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=opt,
        )
        opt.archive()

        api_client.force_login(plan_admin_user)
        url = reverse('action-list', args=(plan.pk,))
        payload = [
            {
                'id': action.pk,
                'identifier': action.identifier,
                'name': action.name,
                'choice_attributes': {
                    action_attribute_type__ordered_choice.identifier: opt.pk,
                },
            },
        ]

        response = api_client.put(url, data=payload)

        assert response.status_code == 200, response.content
        assert (
            AttributeChoice.objects.filter(
                type=action_attribute_type__ordered_choice,
                content_type=action_ct,
                object_id=action.pk,
                choice=opt,
            ).count()
            == 1
        ), 'the existing archived AttributeChoice should still be present'


# =============================================================================
# 8. Inline formset: archive-on-delete + hard-delete fallback
# =============================================================================


class TestArchivableFormset:
    """The choice_options inline formset archives referenced options on delete."""

    def _build_formset(
        self,
        attribute_type: AttributeType,
        options: list[AttributeTypeChoiceOption],
        delete_pk: int,
    ):
        from modelcluster.forms import childformset_factory

        from aplans.utils import ArchivableOrderedModelChildFormSet

        FormSet: Any = childformset_factory(
            AttributeType,
            AttributeTypeChoiceOption,
            formset=cast('Any', ArchivableOrderedModelChildFormSet),
            fields=['name'],
            can_delete=True,
            extra=0,
        )

        prefix = 'choice_options'
        data = {
            f'{prefix}-TOTAL_FORMS': str(len(options)),
            f'{prefix}-INITIAL_FORMS': str(len(options)),
            f'{prefix}-MIN_NUM_FORMS': '0',
            f'{prefix}-MAX_NUM_FORMS': '1000',
        }
        for i, option in enumerate(options):
            data[f'{prefix}-{i}-id'] = str(option.pk)
            data[f'{prefix}-{i}-name'] = option.name
            data[f'{prefix}-{i}-ORDER'] = str(i)
            if option.pk == delete_pk:
                data[f'{prefix}-{i}-DELETE'] = 'on'

        return FormSet(data=data, instance=attribute_type, prefix=prefix)

    def test_delete_existing_archives_referenced_option(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        kept = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Kept',
        )
        referenced = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Referenced',
        )
        action = ActionFactory.create(plan=plan)
        AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=referenced,
        )

        formset = self._build_formset(
            action_attribute_type__ordered_choice,
            [kept, referenced],
            delete_pk=referenced.pk,
        )
        assert formset.is_valid(), formset.errors

        formset.save(commit=True)

        # The referenced option is archived, not deleted.
        referenced.refresh_from_db()
        assert referenced.is_active is False

        # The live AttributeChoice row that pointed at it is still there.
        assert AttributeChoice.objects.filter(choice=referenced).exists()

        # The other option stays put.
        assert AttributeTypeChoiceOption.objects.filter(pk=kept.pk, is_active=True).exists()

    def test_archive_is_recorded_for_post_save_notification(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        kept = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Kept',
        )
        referenced = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Referenced',
        )
        action = ActionFactory.create(plan=plan)
        AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=referenced,
        )

        formset = self._build_formset(
            action_attribute_type__ordered_choice,
            [kept, referenced],
            delete_pk=referenced.pk,
        )
        assert formset.is_valid(), formset.errors

        formset.save(commit=True)

        # The view reads this list to surface a post-save warning to the user.
        assert [o.pk for o in formset.archived_on_last_save] == [referenced.pk]

    def test_archived_on_last_save_is_empty_when_no_archive_happened(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        kept = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Kept',
        )
        unused = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Unused',
        )
        formset = self._build_formset(
            action_attribute_type__ordered_choice,
            [kept, unused],
            delete_pk=unused.pk,
        )
        assert formset.is_valid(), formset.errors
        formset.save(commit=True)

        assert formset.archived_on_last_save == []

    def test_delete_existing_hard_deletes_unreferenced_option(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        kept = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Kept',
        )
        unused = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Unused',
        )

        formset = self._build_formset(
            action_attribute_type__ordered_choice,
            [kept, unused],
            delete_pk=unused.pk,
        )
        assert formset.is_valid(), formset.errors

        formset.save(commit=True)

        assert not AttributeTypeChoiceOption.objects.filter(pk=unused.pk).exists()
        assert AttributeTypeChoiceOption.objects.filter(pk=kept.pk, is_active=True).exists()

    def test_archive_a_non_last_referenced_option_does_not_collide_on_order(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # If the archived option isn't the last in order, the parent
        # OrderedModelChildFormSet compacts the remaining rows starting at
        # order 0. The archived row must be moved out of the active range
        # *before* that compaction runs — otherwise the freshly compacted
        # active row collides with the still-unchanged archived row on
        # (type, order).
        first = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Archived first',
        )
        second = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Second',
        )
        action = ActionFactory.create(plan=plan)
        AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=first,
        )

        formset = self._build_formset(
            action_attribute_type__ordered_choice,
            [first, second],
            delete_pk=first.pk,
        )
        assert formset.is_valid(), formset.errors

        # Must not raise IntegrityError.
        formset.save(commit=True)

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.is_active is False
        assert second.is_active is True
        assert first.order != second.order


# =============================================================================
# 9. Unarchive admin view
# =============================================================================


class TestUnarchiveView:
    """The unarchive admin URL restores an archived option to active."""

    def _unarchive_url(self, attribute_type: AttributeType, option: AttributeTypeChoiceOption) -> str:
        return f'/admin/actions/attributetype/{attribute_type.pk}/unarchive-choice-option/{option.pk}/'

    def test_post_unarchives_option(
        self,
        client,
        plan_admin_user,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Bring back',
        )
        option.archive()
        option.refresh_from_db()
        assert option.is_active is False

        client.force_login(plan_admin_user)
        response = client.post(
            self._unarchive_url(action_attribute_type__ordered_choice, option),
        )

        assert response.status_code == 302
        option.refresh_from_db()
        assert option.is_active is True

    def test_get_is_rejected(
        self,
        client,
        plan_admin_user,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # State-changing endpoint should refuse GET.
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Stays archived',
        )
        option.archive()

        client.force_login(plan_admin_user)
        response = client.get(
            self._unarchive_url(action_attribute_type__ordered_choice, option),
        )

        assert response.status_code == 405
        option.refresh_from_db()
        assert option.is_active is False

    def test_unauthenticated_request_is_redirected_to_login(
        self,
        client,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Stays archived',
        )
        option.archive()

        response = client.post(
            self._unarchive_url(action_attribute_type__ordered_choice, option),
        )

        assert response.status_code in (302, 403)
        option.refresh_from_db()
        assert option.is_active is False

    def test_option_for_wrong_attribute_type_returns_404(
        self,
        client,
        plan_admin_user,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        other_type = AttributeTypeFactory.create(
            object_content_type=ContentType.objects.get_for_model(Action),
            scope=plan,
            format=AttributeType.AttributeFormat.ORDERED_CHOICE,
            name='Other',
        )
        option = AttributeTypeChoiceOptionFactory.create(
            type=other_type,
            name='Belongs to other type',
        )
        option.archive()

        client.force_login(plan_admin_user)
        response = client.post(
            self._unarchive_url(action_attribute_type__ordered_choice, option),
        )

        assert response.status_code == 404
        option.refresh_from_db()
        assert option.is_active is False


# =============================================================================
# 10. ChoiceOptionArchivePanel (badge + unarchive button)
# =============================================================================


class TestArchivePanel:
    """The inline archive panel surfaces archive state and an unarchive button."""

    def _bound_panel(self, option: AttributeTypeChoiceOption):
        from actions.attribute_type_admin import ChoiceOptionArchivePanel

        panel = ChoiceOptionArchivePanel().bind_to_model(AttributeTypeChoiceOption)
        return panel.get_bound_panel(instance=option)

    def test_hidden_for_active_option(
        self,
        attribute_type_choice_option: AttributeTypeChoiceOption,
    ):
        bound = self._bound_panel(attribute_type_choice_option)
        assert bound.is_shown() is False

    def test_shown_for_archived_option(
        self,
        attribute_type_choice_option: AttributeTypeChoiceOption,
    ):
        attribute_type_choice_option.archive()
        attribute_type_choice_option.refresh_from_db()

        bound = self._bound_panel(attribute_type_choice_option)
        assert bound.is_shown() is True

    def test_renders_badge_and_unarchive_button(
        self,
        attribute_type_choice_option: AttributeTypeChoiceOption,
    ):
        attribute_type_choice_option.archive()
        attribute_type_choice_option.refresh_from_db()
        bound = self._bound_panel(attribute_type_choice_option)

        html = bound.render_html()

        assert 'Archived' in html
        assert 'Unarchive' in html
        # The unarchive button must point at the correct admin URL.
        expected_path = (
            f'/admin/actions/attributetype/{attribute_type_choice_option.type_id}/'
            f'unarchive-choice-option/{attribute_type_choice_option.pk}/'
        )
        assert expected_path in html

    def test_unsaved_option_is_not_shown(
        self,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        # An option being added via the inline editor has no pk yet — the
        # panel must not try to construct an unarchive URL for it.
        option = AttributeTypeChoiceOption(
            type=action_attribute_type__ordered_choice,
            name='Not saved',
            is_active=False,
        )
        bound = self._bound_panel(option)
        assert bound.is_shown() is False


# =============================================================================
# 11. Post-save notification + usage panel wording
# =============================================================================


class TestArchiveNotification:
    """The edit view warns the user when 'delete' got converted to archive."""

    def test_form_valid_emits_warning_for_each_archived_option(
        self,
        rf,
        plan_admin_user,
        action_attribute_type__ordered_choice: AttributeType,
        monkeypatch,
    ):
        from types import SimpleNamespace

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.http import HttpResponseRedirect

        from actions.attribute_type_admin import AttributeTypeEditView

        first = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='First archived',
        )
        second = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Second archived',
        )

        request = rf.post('/admin/actions/attributetype/edit/1/')
        request.user = plan_admin_user
        request.session = SimpleNamespace()
        request._messages = FallbackStorage(request)

        # The view's super().form_valid would normally trigger model saves and
        # a redirect; we only care about what our own override layers on top.
        monkeypatch.setattr(
            'actions.attribute_type_admin.AplansEditView.form_valid',
            lambda *_a, **_k: HttpResponseRedirect('/done'),
        )

        # The view's __init__ requires modeladmin context we don't need to
        # exercise here; bypass it and set the request directly.
        view = AttributeTypeEditView.__new__(AttributeTypeEditView)
        view.request = request

        archived_formset = SimpleNamespace(archived_on_last_save=[first, second])
        untouched_formset = SimpleNamespace(archived_on_last_save=[])
        no_attr_formset = SimpleNamespace()
        form = SimpleNamespace(
            formsets={
                'choice_options': archived_formset,
                'other': untouched_formset,
                'legacy': no_attr_formset,
            },
        )

        response = view.form_valid(form)

        assert response.status_code == 302
        messages_emitted = [str(m) for m in request._messages]
        assert any('First archived' in m for m in messages_emitted)
        assert any('Second archived' in m for m in messages_emitted)
        # No spurious messages for the formsets without archived items.
        assert len(messages_emitted) == 2

    def test_form_valid_emits_nothing_when_no_archives_happened(
        self,
        rf,
        plan_admin_user,
        monkeypatch,
    ):
        from types import SimpleNamespace

        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.http import HttpResponseRedirect

        from actions.attribute_type_admin import AttributeTypeEditView

        request = rf.post('/admin/actions/attributetype/edit/1/')
        request.user = plan_admin_user
        request.session = SimpleNamespace()
        request._messages = FallbackStorage(request)
        monkeypatch.setattr(
            'actions.attribute_type_admin.AplansEditView.form_valid',
            lambda *_a, **_k: HttpResponseRedirect('/done'),
        )

        # The view's __init__ requires modeladmin context we don't need to
        # exercise here; bypass it and set the request directly.
        view = AttributeTypeEditView.__new__(AttributeTypeEditView)
        view.request = request

        formset = SimpleNamespace(archived_on_last_save=[])
        form = SimpleNamespace(formsets={'choice_options': formset})

        view.form_valid(form)

        assert list(request._messages) == []


class TestUsagePanelWording:
    """The usage panel explains that deletion becomes archive when in use."""

    def test_panel_mentions_archive_behavior(
        self,
        plan: Plan,
        action_attribute_type__ordered_choice: AttributeType,
    ):
        from actions.attribute_type_admin import (
            ChoiceOptionUsagePanel,
            _get_choice_option_usage,
        )

        # Create an option that's referenced by a live action attribute, so
        # the usage panel surfaces it.
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Used',
        )
        action = ActionFactory.create(plan=plan)
        AttributeChoiceFactory.create(
            type=action_attribute_type__ordered_choice,
            content_object=action,
            choice=option,
        )

        usage = _get_choice_option_usage(action_attribute_type__ordered_choice)
        assert option.pk in usage

        panel = ChoiceOptionUsagePanel(usage).bind_to_model(AttributeTypeChoiceOption)
        bound = panel.get_bound_panel(instance=option)
        html = bound.render_html()

        assert 'archived' in html.lower()
        # The new wording should not still say "delete in all these objects".
        assert 'delete' in html.lower()
        assert 'remove' in html.lower() or 'removed' in html.lower()
