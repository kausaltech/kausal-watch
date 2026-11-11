"""The action edit form is built for the plan, the user and the draft of each request."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType

import pytest

from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin

from actions.models import Action, AttributeText, AttributeType
from actions.tests import action_admin_helpers as h
from actions.tests.factories import ActionFactory, AttributeTypeFactory, PlanFactory
from admin_site.tests.factories import BuiltInFieldCustomizationFactory

pytestmark = pytest.mark.django_db


def text_attribute_type(plan) -> AttributeType:
    return AttributeTypeFactory.create(
        scope=plan,
        object_content_type=ContentType.objects.get_for_model(Action),
        format=AttributeType.AttributeFormat.TEXT,
    )


def field_name(attribute_type: AttributeType) -> str:
    return f'attribute_type_{attribute_type.pk}'


def form_fields(client, user, action) -> set[str]:
    client.force_login(user)
    return set(client.get(h.edit_url(action)).context['form'].fields)


def attribute_texts(action, attribute_type) -> list[str]:
    content_type = ContentType.objects.get_for_model(Action)
    attributes = AttributeText.objects.filter(type=attribute_type, content_type=content_type, object_id=action.pk)
    return [attribute.text for attribute in attributes]


def test_form_has_the_attribute_fields_of_the_actions_plan(client):
    action = ActionFactory.create()
    other_action = ActionFactory.create()
    attribute_type = text_attribute_type(action.plan)
    other_attribute_type = text_attribute_type(other_action.plan)

    fields = form_fields(client, h.make_plan_admin(action.plan), action)
    other_fields = form_fields(client, h.make_plan_admin(other_action.plan), other_action)

    assert field_name(attribute_type) in fields
    assert field_name(other_attribute_type) not in fields
    assert field_name(other_attribute_type) in other_fields
    assert field_name(attribute_type) not in other_fields


def test_form_leaves_out_a_field_restricted_from_the_user(client):
    action = ActionFactory.create()
    BuiltInFieldCustomizationFactory.create(
        plan=action.plan,
        field_name='lead_paragraph',
        instances_visible_for=InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
        instances_editable_by=InstancesEditableByMixin.EditableBy.PLAN_ADMINS,
    )

    assert 'lead_paragraph' not in form_fields(client, h.make_contact_person(action), action)
    assert 'lead_paragraph' in form_fields(client, h.make_plan_admin(action.plan), action)


def test_restricted_field_cannot_be_written_by_posting(client):
    action = ActionFactory.create(lead_paragraph='Original')
    BuiltInFieldCustomizationFactory.create(
        plan=action.plan,
        field_name='lead_paragraph',
        instances_visible_for=InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
        instances_editable_by=InstancesEditableByMixin.EditableBy.PLAN_ADMINS,
    )

    response = h.post_edit(client, h.make_contact_person(action), action, lead_paragraph='Changed')

    assert response.status_code == 302
    action.refresh_from_db()
    assert action.lead_paragraph == 'Original'


def test_attribute_is_stored_at_once_without_moderation(client):
    action = ActionFactory.create()
    attribute_type = text_attribute_type(action.plan)

    response = h.post_edit(client, h.make_plan_admin(action.plan), action, **{field_name(attribute_type): 'Some text'})

    assert response.status_code == 302
    assert attribute_texts(action, attribute_type) == ['Some text']


def test_draft_attribute_is_shown_in_the_form_and_stored_on_publishing(client):
    plan = PlanFactory.create()
    h.enable_moderation(plan)
    action = ActionFactory.create(plan=plan)
    attribute_type = text_attribute_type(plan)
    editor = h.make_contact_person(action)
    plan_admin = h.make_plan_admin(plan)

    h.post_edit(client, editor, action, **{field_name(attribute_type): 'Draft text'})

    assert attribute_texts(action, attribute_type) == []
    response = client.get(h.edit_url(action))
    assert response.context['form'][field_name(attribute_type)].value() == 'Draft text'

    h.post_edit(client, plan_admin, action, 'publish')

    assert attribute_texts(action, attribute_type) == ['Draft text']
