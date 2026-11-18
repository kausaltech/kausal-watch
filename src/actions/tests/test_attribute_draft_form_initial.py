"""
Initial values of attribute form fields when editing a draft.

A draft only carries the attribute types that were fields in its author's form, so a draft saved by
someone who could not edit an attribute type does not contain it. Whoever edits that draft next must
still see the stored value of such a type; a blank field would be saved as empty and, once
published, wipe the stored value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from actions.attributes import AttributeFieldPanel, AttributeType as AttributeTypeWrapper, DraftAttributes
from actions.tests.factories import (
    ActionFactory,
    AttributeCategoryChoiceFactory,
    AttributeChoiceFactory,
    AttributeChoiceWithTextFactory,
    AttributeNumericValueFactory,
    AttributeRichTextFactory,
    AttributeTextFactory,
    AttributeTypeChoiceOptionFactory,
    CategoryFactory,
)

if TYPE_CHECKING:
    from actions.attributes import FormField
    from actions.models import Action, AttributeType, Plan
    from users.models import User

pytestmark = pytest.mark.django_db


def initial_values(attribute_type: AttributeType, user: User, action: Action, draft: DraftAttributes | None) -> dict[str, object]:
    wrapper: AttributeTypeWrapper[Any] = AttributeTypeWrapper.from_model_instance(attribute_type)
    fields: list[FormField] = wrapper.get_form_fields(user, action.plan, action, draft_attributes=draft)
    return {f.name: f.django_field.initial for f in fields}


@pytest.fixture
def action(plan: Plan) -> Action:
    return ActionFactory.create(plan=plan)


def test_text_attribute_missing_from_draft_shows_stored_value(plan_admin_user, action, action_attribute_type__text):
    AttributeTextFactory.create(type=action_attribute_type__text, content_object=action, text='Stored text')

    initial = initial_values(action_attribute_type__text, plan_admin_user, action, DraftAttributes())

    assert initial[f'attribute_type_{action_attribute_type__text.pk}'] == 'Stored text'


def test_rich_text_attribute_missing_from_draft_shows_stored_value(plan_admin_user, action, action_attribute_type__rich_text):
    AttributeRichTextFactory.create(type=action_attribute_type__rich_text, content_object=action, text='<p>Stored</p>')

    initial = initial_values(action_attribute_type__rich_text, plan_admin_user, action, DraftAttributes())

    assert initial[f'attribute_type_{action_attribute_type__rich_text.pk}'] == '<p>Stored</p>'


def test_ordered_choice_attribute_missing_from_draft_shows_stored_value(
    plan_admin_user, action, action_attribute_type__ordered_choice
):
    option = AttributeTypeChoiceOptionFactory.create(type=action_attribute_type__ordered_choice)
    AttributeChoiceFactory.create(type=action_attribute_type__ordered_choice, content_object=action, choice=option)

    initial = initial_values(action_attribute_type__ordered_choice, plan_admin_user, action, DraftAttributes())

    assert initial[f'attribute_type_{action_attribute_type__ordered_choice.pk}'] == option


def test_optional_choice_attribute_missing_from_draft_shows_stored_value(
    plan_admin_user, action, action_attribute_type__optional_choice
):
    at = action_attribute_type__optional_choice
    option = AttributeTypeChoiceOptionFactory.create(type=at)
    AttributeChoiceWithTextFactory.create(type=at, content_object=action, choice=option, text='<p>Why</p>')

    initial = initial_values(at, plan_admin_user, action, DraftAttributes())

    assert initial[f'attribute_type_{at.pk}_choice'] == option
    assert initial[f'attribute_type_{at.pk}_text'] == '<p>Why</p>'


def test_numeric_attribute_missing_from_draft_shows_stored_value(plan_admin_user, action, action_attribute_type__numeric):
    AttributeNumericValueFactory.create(type=action_attribute_type__numeric, content_object=action, value=1.5)

    initial = initial_values(action_attribute_type__numeric, plan_admin_user, action, DraftAttributes())

    assert initial[f'attribute_type_{action_attribute_type__numeric.pk}'] == 1.5


def test_category_choice_attribute_missing_from_draft_shows_stored_value(
    plan_admin_user, action, action_attribute_type__category_choice
):
    at = action_attribute_type__category_choice
    category = CategoryFactory.create(type=at.attribute_category_type)
    attribute = AttributeCategoryChoiceFactory.create(type=at, content_object=action)
    attribute.categories.set([category])
    attribute.save()

    initial = initial_values(at, plan_admin_user, action, DraftAttributes())

    assert initial[f'attribute_type_{at.pk}'] == [category]


def test_value_in_draft_wins_over_stored_value(plan_admin_user, action, action_attribute_type__text):
    AttributeTextFactory.create(type=action_attribute_type__text, content_object=action, text='Stored text')
    wrapper: AttributeTypeWrapper[Any] = AttributeTypeWrapper.from_model_instance(action_attribute_type__text)
    draft = DraftAttributes()
    draft.update(wrapper, wrapper.VALUE_CLASS.from_serialized_value({'text': ''}))

    initial = initial_values(action_attribute_type__text, plan_admin_user, action, draft)

    # The draft's author cleared the value on purpose
    assert initial[f'attribute_type_{action_attribute_type__text.pk}'] == ''


def test_read_only_panel_shows_stored_value_when_draft_lacks_it(
    rf, plan_admin_user, action, action_attribute_type__text, action_attribute_type__rich_text, workflow_factory
):
    from actions.models import Action

    action.plan.features.moderation_workflow = workflow_factory()
    action.plan.features.save()
    AttributeTextFactory.create(type=action_attribute_type__text, content_object=action, text='Stored text')
    # A pending draft whose author could only edit the other attribute type
    rich_text: AttributeTypeWrapper[Any] = AttributeTypeWrapper.from_model_instance(action_attribute_type__rich_text)
    action.draft_attributes = DraftAttributes()
    action.draft_attributes.update(rich_text, rich_text.VALUE_CLASS.from_serialized_value({'text': '<p>Draft</p>'}))
    action.save_revision(user=plan_admin_user)
    action.refresh_from_db()
    assert action.has_unpublished_changes

    wrapper: AttributeTypeWrapper[Any] = AttributeTypeWrapper.from_model_instance(action_attribute_type__text)
    fields = wrapper.get_form_fields(plan_admin_user, action.plan, action, include_read_only_fields=True)
    [field] = [f for f in fields if not f.language]
    request = rf.get('/')
    request.user = plan_admin_user
    bound_panel = cast(
        'AttributeFieldPanel.BoundPanel[Action]',
        field.get_panel().bind_to_model(Action).get_bound_panel(instance=action, request=request, form=None),
    )

    assert bound_panel.value_from_instance() == 'Stored text'
