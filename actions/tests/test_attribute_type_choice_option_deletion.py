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

from typing import TYPE_CHECKING

import reversion
from django.contrib.contenttypes.models import ContentType

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
        attr_type_wrapper: AttributeTypeWrapper = (
            AttributeTypeWrapper.from_model_instance(action_attribute_type__optional_choice)
        )
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
            at for at in data['plan']['actionAttributeTypes']
            if at['name'] == action_attribute_type__ordered_choice.name
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
