"""
Pledge attribute types are scoped to the plan just like action attribute types, but they are not action attributes.

They used to leak into everything that listed a plan's action attribute types by scope alone. The action grid editor
then offered them as action columns, and saving such a column crashed the bulk update with a `KeyError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

import pytest

from actions.api import ActionSerializer, ActionViewSet
from actions.models import Action, Pledge
from actions.models.attributes import AttributeType
from actions.tests.factories import ActionFactory, AttributeTypeChoiceOptionFactory, AttributeTypeFactory

if TYPE_CHECKING:
    from rest_framework.serializers import Serializer

pytestmark = pytest.mark.django_db


def _create_choice_attribute_type(plan, model: type[Action | Pledge]) -> AttributeType:
    return AttributeTypeFactory.create(
        object_content_type=ContentType.objects.get_for_model(model),
        scope=plan,
        format=AttributeType.AttributeFormat.UNORDERED_CHOICE,
    )


@pytest.fixture
def action_attribute_type(plan) -> AttributeType:
    return _create_choice_attribute_type(plan, Action)


@pytest.fixture
def pledge_attribute_type(plan) -> AttributeType:
    return _create_choice_attribute_type(plan, Pledge)


def test_for_actions_excludes_pledge_attribute_types(plan, action_attribute_type, pledge_attribute_type):
    assert list(AttributeType.objects.for_actions(plan)) == [action_attribute_type]
    assert set(AttributeType.objects.for_plan_scope(plan)) == {action_attribute_type, pledge_attribute_type}


def test_graphql_action_attribute_types_exclude_pledge_attribute_types(
    graphql_client_query_data, plan, action_attribute_type, pledge_attribute_type
):
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
            plan(id: $plan) {
                actionAttributeTypes {
                    identifier
                }
            }
        }
        """,
        variables={'plan': plan.identifier},
    )
    identifiers = [at['identifier'] for at in data['plan']['actionAttributeTypes']]
    assert identifiers == [action_attribute_type.identifier]


def test_action_serializer_attribute_fields_exclude_pledge_attribute_types(
    plan, plan_admin_user, action_attribute_type, pledge_attribute_type
):
    request = Request(APIRequestFactory().get('/'))
    request.user = plan_admin_user
    view = ActionViewSet(request=request, kwargs={'plan_pk': plan.pk}, format_kwarg=None, action='list')
    serializer = cast('ActionSerializer', view.get_serializer())
    assert list(cast('Serializer', serializer.fields['choice_attributes']).fields) == [action_attribute_type.identifier]


def _put_choice_attributes(plan, user, action: Action, choice_attributes: dict[str, int]):
    client = APIClient()
    client.raise_request_exception = False
    client.force_authenticate(user)
    payload = [
        {
            'id': action.pk,
            'identifier': action.identifier,
            'name': action.name,
            'version': action.version,
            'choice_attributes': choice_attributes,
        },
    ]
    return client.put(reverse('action-list', args=(plan.pk,)), data=payload, format='json')


def test_action_bulk_update_rejects_pledge_attribute_type(plan, plan_admin_user, pledge_attribute_type):
    action = ActionFactory.create(plan=plan)
    option = AttributeTypeChoiceOptionFactory.create(type=pledge_attribute_type)

    response = _put_choice_attributes(plan, plan_admin_user, action, {pledge_attribute_type.identifier: option.pk})

    assert response.status_code == 400, response.content
    assert pledge_attribute_type.identifier in str(response.json())
    assert not pledge_attribute_type.choice_attributes.exists()


def test_action_bulk_update_still_sets_action_attribute_type(plan, plan_admin_user, action_attribute_type):
    action = ActionFactory.create(plan=plan)
    option = AttributeTypeChoiceOptionFactory.create(type=action_attribute_type)

    response = _put_choice_attributes(plan, plan_admin_user, action, {action_attribute_type.identifier: option.pk})

    assert response.status_code == 200, response.content
    assert action_attribute_type.choice_attributes.get().choice == option
