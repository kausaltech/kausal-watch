"""
The category REST API only deals with the attribute types of the category type it is nested under.

Its attribute fields used to list the plan's action attribute types instead, and writes for attribute types it does not
know crashed with a `KeyError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

import pytest

from actions.api import CategorySerializer, CategoryViewSet
from actions.models import Action
from actions.models.attributes import AttributeType
from actions.tests.factories import (
    AttributeTypeChoiceOptionFactory,
    AttributeTypeFactory,
    CategoryFactory,
    CategoryTypeFactory,
)

if TYPE_CHECKING:
    from rest_framework.serializers import Serializer

    from actions.models import Category, CategoryType, Plan
    from users.models import User

pytestmark = pytest.mark.django_db

CHOICE = AttributeType.AttributeFormat.UNORDERED_CHOICE


@pytest.fixture
def own_attribute_type(category_type) -> AttributeType:
    return AttributeTypeFactory.create(scope=category_type, format=CHOICE)


@pytest.fixture
def other_category_type_attribute_type(plan) -> AttributeType:
    other_category_type = CategoryTypeFactory.create(plan=plan)
    return AttributeTypeFactory.create(scope=other_category_type, format=CHOICE)


@pytest.fixture
def action_attribute_type(plan) -> AttributeType:
    return AttributeTypeFactory.create(
        object_content_type=ContentType.objects.get_for_model(Action),
        scope=plan,
        format=CHOICE,
    )


def _choice_attribute_field_names(plan: Plan, category_type: CategoryType, user: User) -> list[str]:
    request = Request(APIRequestFactory().get('/'))
    request.user = user
    view = CategoryViewSet(
        request=request,
        kwargs={'plan_pk': plan.pk, 'category_type_pk': category_type.pk},
        format_kwarg=None,
        action='list',
    )
    serializer = cast('CategorySerializer', view.get_serializer())
    return list(cast('Serializer', serializer.fields['choice_attributes']).fields)


def test_attribute_fields_are_those_of_the_category_type(
    plan,
    category_type,
    plan_admin_user,
    own_attribute_type,
    other_category_type_attribute_type,
    action_attribute_type,
):
    field_names = _choice_attribute_field_names(plan, category_type, plan_admin_user)
    assert field_names == [own_attribute_type.identifier]


def _put_choice_attributes(plan: Plan, user: User, category: Category, choice_attributes: dict[str, int]):
    data = dict(CategorySerializer(category).data)
    data['choice_attributes'] = choice_attributes
    client = APIClient()
    client.raise_request_exception = False
    client.force_authenticate(user)
    url = reverse('category-list', args=(plan.pk, category.type.pk))
    return client.put(url, data=[data], format='json')


def test_bulk_update_sets_attribute_of_the_category_type(plan, category_type, plan_admin_user, own_attribute_type):
    category = CategoryFactory.create(type=category_type)
    option = AttributeTypeChoiceOptionFactory.create(type=own_attribute_type)

    response = _put_choice_attributes(plan, plan_admin_user, category, {own_attribute_type.identifier: option.pk})

    assert response.status_code == 200, response.content
    assert own_attribute_type.choice_attributes.get().choice == option


@pytest.mark.parametrize('foreign_attribute_type', ['other_category_type_attribute_type', 'action_attribute_type'])
def test_bulk_update_rejects_attribute_type_of_another_scope(
    plan, category_type, plan_admin_user, foreign_attribute_type, request
):
    attribute_type: AttributeType = request.getfixturevalue(foreign_attribute_type)
    category = CategoryFactory.create(type=category_type)
    option = AttributeTypeChoiceOptionFactory.create(type=attribute_type)

    response = _put_choice_attributes(plan, plan_admin_user, category, {attribute_type.identifier: option.pk})

    assert response.status_code == 400, response.content
    assert attribute_type.identifier in str(response.json())
    assert not attribute_type.choice_attributes.exists()
