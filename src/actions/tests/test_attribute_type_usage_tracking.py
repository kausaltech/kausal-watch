"""
Tests for AttributeType and AttributeTypeChoiceOption usage tracking functionality.

These tests verify that the usage tracking system correctly identifies:
- Published objects using attribute types and choice options
- Reports that would be affected by attribute deletion
- Proper label generation for different model types
"""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.contenttypes.models import ContentType

import pytest

from actions.attribute_type_admin import (
    ATTRIBUTE_VALUE_MODELS,
    AttributeTypeUsageInfo,
    ChoiceOptionUsageInfo,
    ChoiceOptionUsagePanel,
    _collect_published_for_attribute_type,
    _collect_published_per_option,
    _collect_reports_for_attribute_type,
    _draft_label,
    _extract_choice_pk_from_revision_value,
    _get_attribute_type_usage,
    _get_choice_option_usage,
    _published_label,
    check_attribute_value_models,
)
from actions.models import Action, AttributeType, Category, Pledge
from actions.tests.factories import (
    ActionFactory,
    AttributeChoiceFactory,
    AttributeChoiceWithTextFactory,
    AttributeTypeChoiceOptionFactory,
    AttributeTypeFactory,
    CategoryFactory,
    CategoryTypeFactory,
    PledgeFactory,
)
from reports.tests.factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db


# =============================================================================
# Helper Functions
# =============================================================================


def get_action_content_type():
    """Get the ContentType for Action model."""
    return ContentType.objects.get_for_model(Action)


def get_category_content_type():
    """Get the ContentType for Category model."""
    return ContentType.objects.get_for_model(Category)


def get_pledge_content_type():
    """Get the ContentType for Pledge model."""
    return ContentType.objects.get_for_model(Pledge)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def action_attribute_type_ordered_choice(plan):
    """Create an ordered choice attribute type scoped to the plan."""
    return AttributeTypeFactory.create(
        object_content_type=get_action_content_type(),
        scope=plan,
        format=AttributeType.AttributeFormat.ORDERED_CHOICE,
        name='Test Ordered Choice',
    )


@pytest.fixture
def action_attribute_type_optional_choice_with_text(plan):
    """Create an optional choice with text attribute type scoped to the plan."""
    return AttributeTypeFactory.create(
        object_content_type=get_action_content_type(),
        scope=plan,
        format=AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT,
        name='Test Optional Choice With Text',
    )


@pytest.fixture
def category_attribute_type_ordered_choice(plan):
    """Create an ordered choice attribute type for categories."""
    return AttributeTypeFactory.create(
        object_content_type=get_category_content_type(),
        scope=plan,
        format=AttributeType.AttributeFormat.ORDERED_CHOICE,
        name='Category Choice Field',
    )


@pytest.fixture
def pledge_attribute_type_ordered_choice(plan):
    """Create an ordered choice attribute type for pledges."""
    return AttributeTypeFactory.create(
        object_content_type=get_pledge_content_type(),
        scope=plan,
        format=AttributeType.AttributeFormat.ORDERED_CHOICE,
        name='Pledge Choice Field',
    )


@pytest.fixture
def choice_option_a(action_attribute_type_ordered_choice):
    """Create a choice option A."""
    return AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type_ordered_choice,
        name='Option A',
    )


@pytest.fixture
def choice_option_b(action_attribute_type_ordered_choice):
    """Create a choice option B."""
    return AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type_ordered_choice,
        name='Option B',
    )


@pytest.fixture
def choice_option_c(action_attribute_type_optional_choice_with_text):
    """Create a choice option C for optional choice with text."""
    return AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type_optional_choice_with_text,
        name='Option C',
    )


# =============================================================================
# Tests for _extract_choice_pk_from_revision_value
# =============================================================================


class TestExtractChoicePkFromRevisionValue:
    """Test extraction of choice PKs from serialized revision values."""

    def test_ordered_choice_with_int_value(self):
        """Test extracting PK from ordered_choice format with int value."""
        pk = _extract_choice_pk_from_revision_value('ordered_choice', 42)
        assert pk == 42

    def test_unordered_choice_with_int_value(self):
        """Test extracting PK from unordered_choice format with int value."""
        pk = _extract_choice_pk_from_revision_value('unordered_choice', 99)
        assert pk == 99

    def test_optional_choice_with_dict_value(self):
        """Test extracting PK from optional_choice format with dict value."""
        value = {'choice': 123, 'text': {'en': 'Some text'}}
        pk = _extract_choice_pk_from_revision_value('optional_choice', value)
        assert pk == 123

    def test_optional_choice_without_choice_key(self):
        """Test handling optional_choice dict without 'choice' key."""
        value = {'text': {'en': 'Some text'}}
        pk = _extract_choice_pk_from_revision_value('optional_choice', value)
        assert pk is None

    def test_ordered_choice_with_non_int_value(self):
        """Test handling ordered_choice with non-int value."""
        pk = _extract_choice_pk_from_revision_value('ordered_choice', 'invalid')
        assert pk is None

    def test_optional_choice_with_non_dict_value(self):
        """Test handling optional_choice with non-dict value."""
        pk = _extract_choice_pk_from_revision_value('optional_choice', 'invalid')
        assert pk is None

    def test_unknown_format_key(self):
        """Test handling unknown format key."""
        pk = _extract_choice_pk_from_revision_value('text', 'some text')
        assert pk is None


# =============================================================================
# Tests for _collect_published_per_option
# =============================================================================


class TestCollectPublishedPerOption:
    """Test collecting published objects per choice option."""

    def test_no_published_objects(self, action_attribute_type_ordered_choice, choice_option_a):
        """Test with no published objects using the choice options."""
        option_pks = {choice_option_a.pk}
        result = _collect_published_per_option(action_attribute_type_ordered_choice, option_pks)
        assert result == {}

    def test_single_published_action_with_attribute_choice(
        self,
        plan,
        action_attribute_type_ordered_choice,
        choice_option_a,
    ):
        """Test collecting a single published action with AttributeChoice."""
        action = ActionFactory.create(plan=plan, name='Action 1')
        AttributeChoiceFactory.create(
            type=action_attribute_type_ordered_choice,
            content_type=get_action_content_type(),
            object_id=action.pk,
            choice=choice_option_a,
        )

        option_pks = {choice_option_a.pk}
        result = _collect_published_per_option(action_attribute_type_ordered_choice, option_pks)

        assert choice_option_a.pk in result
        assert len(result[choice_option_a.pk]) == 1
        assert result[choice_option_a.pk][0] == str(action)

    def test_multiple_actions_same_option(
        self,
        plan,
        action_attribute_type_ordered_choice,
        choice_option_a,
    ):
        """Test collecting multiple actions using the same choice option."""
        action1 = ActionFactory.create(plan=plan, name='Action 1')
        action2 = ActionFactory.create(plan=plan, name='Action 2')

        for action in [action1, action2]:
            AttributeChoiceFactory.create(
                type=action_attribute_type_ordered_choice,
                content_type=get_action_content_type(),
                object_id=action.pk,
                choice=choice_option_a,
            )

        option_pks = {choice_option_a.pk}
        result = _collect_published_per_option(action_attribute_type_ordered_choice, option_pks)

        assert choice_option_a.pk in result
        assert len(result[choice_option_a.pk]) == 2
        names = set(result[choice_option_a.pk])
        assert str(action1) in names
        assert str(action2) in names

    def test_multiple_options_different_actions(
        self,
        plan,
        action_attribute_type_ordered_choice,
        choice_option_a,
        choice_option_b,
    ):
        """Test collecting actions distributed across multiple choice options."""
        action1 = ActionFactory.create(plan=plan, name='Action 1')
        action2 = ActionFactory.create(plan=plan, name='Action 2')

        AttributeChoiceFactory.create(
            type=action_attribute_type_ordered_choice,
            content_type=get_action_content_type(),
            object_id=action1.pk,
            choice=choice_option_a,
        )
        AttributeChoiceFactory.create(
            type=action_attribute_type_ordered_choice,
            content_type=get_action_content_type(),
            object_id=action2.pk,
            choice=choice_option_b,
        )

        option_pks = {choice_option_a.pk, choice_option_b.pk}
        result = _collect_published_per_option(action_attribute_type_ordered_choice, option_pks)

        assert choice_option_a.pk in result
        assert choice_option_b.pk in result
        assert len(result[choice_option_a.pk]) == 1
        assert len(result[choice_option_b.pk]) == 1
        assert result[choice_option_a.pk][0] == str(action1)
        assert result[choice_option_b.pk][0] == str(action2)

    def test_attribute_choice_with_text(
        self,
        plan,
        action_attribute_type_optional_choice_with_text,
        choice_option_c,
    ):
        """Test collecting objects with AttributeChoiceWithText."""
        action = ActionFactory.create(plan=plan, name='Action 1')
        AttributeChoiceWithTextFactory.create(
            type=action_attribute_type_optional_choice_with_text,
            content_type=get_action_content_type(),
            object_id=action.pk,
            choice=choice_option_c,
        )

        option_pks = {choice_option_c.pk}
        result = _collect_published_per_option(
            action_attribute_type_optional_choice_with_text,
            option_pks,
        )

        assert choice_option_c.pk in result
        assert len(result[choice_option_c.pk]) == 1
        assert result[choice_option_c.pk][0] == str(action)

    def test_only_requested_options_included(
        self,
        plan,
        action_attribute_type_ordered_choice,
        choice_option_a,
        choice_option_b,
    ):
        """Test that only requested option PKs are included in results."""
        action1 = ActionFactory.create(plan=plan, name='Action 1')
        action2 = ActionFactory.create(plan=plan, name='Action 2')

        AttributeChoiceFactory.create(
            type=action_attribute_type_ordered_choice,
            content_type=get_action_content_type(),
            object_id=action1.pk,
            choice=choice_option_a,
        )
        AttributeChoiceFactory.create(
            type=action_attribute_type_ordered_choice,
            content_type=get_action_content_type(),
            object_id=action2.pk,
            choice=choice_option_b,
        )

        # Only request option A
        option_pks = {choice_option_a.pk}
        result = _collect_published_per_option(action_attribute_type_ordered_choice, option_pks)

        assert choice_option_a.pk in result
        assert choice_option_b.pk not in result


# =============================================================================
# Tests for _collect_published_for_attribute_type
# =============================================================================


class TestCollectPublishedForAttributeType:
    """Test collecting all published objects using an attribute type."""

    def test_no_published_objects(self, action_attribute_type_ordered_choice):
        """Test with no objects using the attribute type."""
        result = _collect_published_for_attribute_type(action_attribute_type_ordered_choice)
        assert result == []

    def test_different_attribute_value_types(
        self,
        plan,
        action_attribute_type_ordered_choice,
        choice_option_a,
    ):
        """Test that all attribute value model types are checked."""
        action = ActionFactory.create(plan=plan, name='Action 1')
        AttributeChoiceFactory.create(
            type=action_attribute_type_ordered_choice,
            content_type=get_action_content_type(),
            object_id=action.pk,
            choice=choice_option_a,
        )

        result = _collect_published_for_attribute_type(action_attribute_type_ordered_choice)

        assert len(result) == 1
        assert result[0] == str(action)


# =============================================================================
# Tests for _collect_reports_for_attribute_type
# =============================================================================


class TestCollectReportsForAttributeType:
    """Test collecting incomplete reports for attribute types."""

    def test_non_action_attribute_returns_empty(self, category_attribute_type_ordered_choice):
        """Test that non-action attribute types return empty list."""
        result = _collect_reports_for_attribute_type(category_attribute_type_ordered_choice)
        assert result == []

    def test_no_reports(self, action_attribute_type_ordered_choice):
        """Test with no reports in the system."""
        result = _collect_reports_for_attribute_type(action_attribute_type_ordered_choice)
        assert result == []

    def test_incomplete_reports(self, plan, action_attribute_type_ordered_choice):
        """Test collecting incomplete reports."""
        report_type = ReportTypeFactory.create(plan=plan)
        report1 = ReportFactory.create(type=report_type, is_complete=False, name='Q1 Report')
        report2 = ReportFactory.create(type=report_type, is_complete=False, name='Q2 Report')

        result = _collect_reports_for_attribute_type(action_attribute_type_ordered_choice)

        assert len(result) == 2
        assert str(report1) in result
        assert str(report2) in result

    def test_ignores_complete_reports(self, plan, action_attribute_type_ordered_choice):
        """Test that complete reports are not included."""
        report_type = ReportTypeFactory.create(plan=plan)
        ReportFactory.create(type=report_type, is_complete=True, name='Complete Report')
        incomplete_report = ReportFactory.create(
            type=report_type,
            is_complete=False,
            name='Incomplete Report',
        )

        result = _collect_reports_for_attribute_type(action_attribute_type_ordered_choice)

        assert len(result) == 1
        assert str(incomplete_report) in result

    def test_only_plan_reports(self, plan, action_attribute_type_ordered_choice):
        """Test that only reports from the same plan are included."""
        from actions.tests.factories import PlanFactory

        other_plan = PlanFactory.create()

        # Report from the attribute type's plan
        report_type1 = ReportTypeFactory.create(plan=plan)
        report1 = ReportFactory.create(type=report_type1, is_complete=False, name='Same Plan Report')

        # Report from a different plan
        report_type2 = ReportTypeFactory.create(plan=other_plan)
        ReportFactory.create(type=report_type2, is_complete=False, name='Other Plan Report')

        result = _collect_reports_for_attribute_type(action_attribute_type_ordered_choice)

        assert len(result) == 1
        assert str(report1) in result


# =============================================================================
# Tests for label functions
# =============================================================================


class TestPublishedLabel:
    """Test _published_label function for different models."""

    def test_action_model_singular(self):
        """Test label for single published action."""
        label = _published_label(Action, 1)
        assert '1' in label
        assert 'action' in label.lower()

    def test_action_model_plural(self):
        """Test label for multiple published actions."""
        label = _published_label(Action, 5)
        assert '5' in label
        assert 'action' in label.lower()

    def test_category_model_singular(self):
        """Test label for single category."""
        label = _published_label(Category, 1)
        assert '1' in label
        assert 'categor' in label.lower()  # category/categories

    def test_category_model_plural(self):
        """Test label for multiple categories."""
        label = _published_label(Category, 3)
        assert '3' in label
        assert 'categor' in label.lower()

    def test_pledge_model_singular(self):
        """Test label for single pledge."""
        label = _published_label(Pledge, 1)
        assert '1' in label
        assert 'pledge' in label.lower()

    def test_pledge_model_plural(self):
        """Test label for multiple pledges."""
        label = _published_label(Pledge, 2)
        assert '2' in label
        assert 'pledge' in label.lower()

    def test_unexpected_model_raises_type_error(self):
        """Test that unexpected model raises TypeError."""

        # Use a mock class that's not in the expected list
        class UnexpectedModel:
            pass

        with pytest.raises(TypeError, match='Unexpected model'):
            _published_label(UnexpectedModel, 1)  # type: ignore[arg-type]


class TestDraftLabel:
    """Test _draft_label function for different models."""

    def test_action_model_singular(self):
        """Test label for single draft action."""
        label = _draft_label(Action, 1)
        assert '1' in label
        assert 'action' in label.lower()
        assert 'draft' in label.lower()

    def test_action_model_plural(self):
        """Test label for multiple draft actions."""
        label = _draft_label(Action, 4)
        assert '4' in label
        assert 'action' in label.lower()
        assert 'draft' in label.lower()

    def test_unexpected_model_raises_type_error(self):
        """Test that unexpected model raises TypeError."""
        with pytest.raises(TypeError, match='Unexpected model'):
            _draft_label(Category, 1)  # type: ignore[arg-type]


# =============================================================================
# Tests for _get_choice_option_usage
# =============================================================================


class TestGetChoiceOptionUsage:
    """Test the main function for getting choice option usage info."""

    def test_no_options_returns_empty(self, action_attribute_type_ordered_choice):
        """Test attribute type with no choice options."""
        result = _get_choice_option_usage(action_attribute_type_ordered_choice)
        assert result == {}

    def test_unused_options_return_empty(
        self,
        action_attribute_type_ordered_choice,
        choice_option_a,
    ):
        """Test that unused choice options are not included in results."""
        result = _get_choice_option_usage(action_attribute_type_ordered_choice)
        assert result == {}

    def test_option_with_published_usage(
        self,
        plan,
        action_attribute_type_ordered_choice,
        choice_option_a,
    ):
        """Test option used in published action."""
        action = ActionFactory.create(plan=plan, name='Action 1')
        AttributeChoiceFactory.create(
            type=action_attribute_type_ordered_choice,
            content_type=get_action_content_type(),
            object_id=action.pk,
            choice=choice_option_a,
        )

        result = _get_choice_option_usage(action_attribute_type_ordered_choice)

        assert choice_option_a.pk in result
        info = result[choice_option_a.pk]
        assert info.published_count == 1
        assert info.draft_count == 0
        assert str(action) in info.published_object_names
        assert info.published_object_label != ''

    def test_option_with_report_usage(
        self,
        plan,
        action_attribute_type_ordered_choice,
        choice_option_a,
    ):
        """Test option used in action that's included in incomplete reports."""
        action = ActionFactory.create(plan=plan, name='Action 1')
        AttributeChoiceFactory.create(
            type=action_attribute_type_ordered_choice,
            content_type=get_action_content_type(),
            object_id=action.pk,
            choice=choice_option_a,
        )

        # Create incomplete report
        report_type = ReportTypeFactory.create(plan=plan)
        report = ReportFactory.create(type=report_type, is_complete=False, name='Q1 Report')

        result = _get_choice_option_usage(action_attribute_type_ordered_choice)

        assert choice_option_a.pk in result
        info = result[choice_option_a.pk]
        assert info.report_count == 1
        assert str(report) in info.report_names

    def test_option_ignores_complete_reports(
        self,
        plan,
        action_attribute_type_ordered_choice,
        choice_option_a,
    ):
        """Test that complete reports are not included in usage."""
        action = ActionFactory.create(plan=plan, name='Action 1')
        AttributeChoiceFactory.create(
            type=action_attribute_type_ordered_choice,
            content_type=get_action_content_type(),
            object_id=action.pk,
            choice=choice_option_a,
        )

        # Create complete report
        report_type = ReportTypeFactory.create(plan=plan)
        ReportFactory.create(type=report_type, is_complete=True, name='Q1 Report')

        result = _get_choice_option_usage(action_attribute_type_ordered_choice)

        assert choice_option_a.pk in result
        info = result[choice_option_a.pk]
        assert info.report_count == 0


# =============================================================================
# Tests for _get_attribute_type_usage
# =============================================================================


class TestGetAttributeTypeUsage:
    """Test the main function for getting attribute type usage info."""

    def test_unused_attribute_type(self, action_attribute_type_ordered_choice):
        """Test attribute type with no usage."""
        result = _get_attribute_type_usage(action_attribute_type_ordered_choice)

        assert isinstance(result, AttributeTypeUsageInfo)
        assert result.published_count == 0
        assert result.draft_count == 0
        assert result.report_count == 0
        assert not result.has_usage

    def test_category_attribute_type(self, plan, category_attribute_type_ordered_choice):
        """Test usage tracking for category attribute types."""
        category_type = CategoryTypeFactory.create(plan=plan)
        category = CategoryFactory.create(type=category_type, name='Category 1')

        choice_option = AttributeTypeChoiceOptionFactory.create(
            type=category_attribute_type_ordered_choice,
        )
        AttributeChoiceFactory.create(
            type=category_attribute_type_ordered_choice,
            content_type=get_category_content_type(),
            object_id=category.pk,
            choice=choice_option,
        )

        result = _get_attribute_type_usage(category_attribute_type_ordered_choice)

        assert result.published_count == 1
        assert result.draft_count == 0  # Categories don't have drafts
        assert result.report_count == 0  # Reports only track actions
        assert str(category) in result.published_object_names
        # Should not have draft_label for non-draft models
        assert result.draft_label == ''

    def test_pledge_attribute_type(self, plan, pledge_attribute_type_ordered_choice):
        """Test usage tracking for pledge attribute types."""
        pledge = PledgeFactory.create(plan=plan, name='Pledge 1')

        choice_option = AttributeTypeChoiceOptionFactory.create(
            type=pledge_attribute_type_ordered_choice,
        )
        AttributeChoiceFactory.create(
            type=pledge_attribute_type_ordered_choice,
            content_type=get_pledge_content_type(),
            object_id=pledge.pk,
            choice=choice_option,
        )

        result = _get_attribute_type_usage(pledge_attribute_type_ordered_choice)

        assert result.published_count == 1
        assert result.draft_count == 0  # Pledges don't have drafts
        assert result.report_count == 0  # Reports only track actions
        assert str(pledge) in result.published_object_names


# =============================================================================
# Tests for ChoiceOptionUsageInfo dataclass
# =============================================================================


class TestChoiceOptionUsageInfo:
    """Test ChoiceOptionUsageInfo dataclass properties."""

    def test_defaults(self):
        """Test default values."""
        info = ChoiceOptionUsageInfo()
        assert info.published_count == 0
        assert info.draft_count == 0
        assert info.report_count == 0
        assert not info.has_usage

    def test_published_count(self):
        """Test published_count property."""
        info = ChoiceOptionUsageInfo(published_object_names=['A', 'B', 'C'])
        assert info.published_count == 3

    def test_draft_count(self):
        """Test draft_count property."""
        info = ChoiceOptionUsageInfo(draft_object_names=['X', 'Y'])
        assert info.draft_count == 2

    def test_report_count(self):
        """Test report_count property."""
        info = ChoiceOptionUsageInfo(report_names=['R1', 'R2', 'R3', 'R4'])
        assert info.report_count == 4

    def test_has_usage_with_published(self):
        """Test has_usage is True when there are published objects."""
        info = ChoiceOptionUsageInfo(published_object_names=['A'])
        assert info.has_usage

    def test_has_usage_with_drafts(self):
        """Test has_usage is True when there are drafts."""
        info = ChoiceOptionUsageInfo(draft_object_names=['X'])
        assert info.has_usage

    def test_has_usage_with_reports(self):
        """Test has_usage is True when there are reports."""
        info = ChoiceOptionUsageInfo(report_names=['R1'])
        assert info.has_usage

    def test_has_usage_false(self):
        """Test has_usage is False when all counts are zero."""
        info = ChoiceOptionUsageInfo()
        assert not info.has_usage

    def test_report_label_singular(self):
        """Test report_label for single report."""
        info = ChoiceOptionUsageInfo(report_names=['R1'])
        label = info.report_label
        assert '1' in label
        assert 'report' in label.lower()

    def test_report_label_plural(self):
        """Test report_label for multiple reports."""
        info = ChoiceOptionUsageInfo(report_names=['R1', 'R2', 'R3'])
        label = info.report_label
        assert '3' in label
        assert 'report' in label.lower()


# =============================================================================
# Tests for AttributeTypeUsageInfo dataclass
# =============================================================================


class TestAttributeTypeUsageInfo:
    """Test AttributeTypeUsageInfo dataclass properties."""

    def test_defaults(self):
        """Test default values."""
        info = AttributeTypeUsageInfo()
        assert info.published_count == 0
        assert info.draft_count == 0
        assert info.report_count == 0
        assert not info.has_usage

    def test_counts(self):
        """Test count properties."""
        info = AttributeTypeUsageInfo(
            published_object_names=['A', 'B'],
            draft_object_names=['X'],
            report_names=['R1', 'R2', 'R3'],
        )
        assert info.published_count == 2
        assert info.draft_count == 1
        assert info.report_count == 3

    def test_has_usage(self):
        """Test has_usage property."""
        # No usage
        info1 = AttributeTypeUsageInfo()
        assert not info1.has_usage

        # Published usage
        info2 = AttributeTypeUsageInfo(published_object_names=['A'])
        assert info2.has_usage

        # Draft usage
        info3 = AttributeTypeUsageInfo(draft_object_names=['X'])
        assert info3.has_usage

        # Report usage
        info4 = AttributeTypeUsageInfo(report_names=['R'])
        assert info4.has_usage


# =============================================================================
# Tests for ChoiceOptionUsagePanel
# =============================================================================


class TestChoiceOptionUsagePanel:
    """Test ChoiceOptionUsagePanel custom panel."""

    def test_panel_initialization(self):
        """Test panel can be initialized with usage data."""
        usage_by_option = {
            1: ChoiceOptionUsageInfo(published_object_names=['Action 1']),
        }
        panel = ChoiceOptionUsagePanel(usage_by_option=usage_by_option)
        assert panel.usage_by_option == usage_by_option

    def test_clone_kwargs(self):
        """Test clone_kwargs includes usage_by_option."""
        usage_by_option = {
            1: ChoiceOptionUsageInfo(published_object_names=['Action 1']),
        }
        panel = ChoiceOptionUsagePanel(usage_by_option=usage_by_option)
        kwargs = panel.clone_kwargs()
        assert 'usage_by_option' in kwargs
        assert kwargs['usage_by_option'] == usage_by_option


# =============================================================================
# Tests for check_attribute_value_models
# =============================================================================


class TestCheckAttributeValueModels:
    """Test check_attribute_value_models validation function."""

    def test_all_models_present(self):
        """Test that all expected attribute value models are in ATTRIBUTE_VALUE_MODELS."""
        from actions.models.attributes import (
            AttributeCategoryChoice,
            AttributeChoice,
            AttributeChoiceWithText,
            AttributeNumericValue,
            AttributeRichText,
            AttributeText,
        )

        # This should not raise any warnings
        check_attribute_value_models()

        # Verify ATTRIBUTE_VALUE_MODELS contains expected models
        assert AttributeChoice in ATTRIBUTE_VALUE_MODELS
        assert AttributeChoiceWithText in ATTRIBUTE_VALUE_MODELS
        assert AttributeText in ATTRIBUTE_VALUE_MODELS
        assert AttributeRichText in ATTRIBUTE_VALUE_MODELS
        assert AttributeNumericValue in ATTRIBUTE_VALUE_MODELS
        assert AttributeCategoryChoice in ATTRIBUTE_VALUE_MODELS

    def test_logs_warning_for_missing_models(self):
        """Test that missing models are logged as warnings."""
        # We can't easily modify ATTRIBUTE_VALUE_MODELS, so we'll patch it
        with (
            patch('actions.attribute_type_admin.ATTRIBUTE_VALUE_MODELS', []),
            patch('actions.attribute_type_admin.logger.warning') as mock_logger,
        ):
            check_attribute_value_models()
            # Should log a warning about missing models
            assert mock_logger.called

    def test_logs_warning_for_extra_models(self):
        """Test that extra models are logged as warnings."""

        # Add a fake class that's not a real Attribute subclass
        class FakeAttribute:
            pass

        fake_list = ATTRIBUTE_VALUE_MODELS + [FakeAttribute]  # type: ignore[list-item]
        with (
            patch('actions.attribute_type_admin.ATTRIBUTE_VALUE_MODELS', fake_list),
            patch('actions.attribute_type_admin.logger.warning') as mock_logger,
        ):
            check_attribute_value_models()
            # Should log a warning about extra models
            assert mock_logger.called
