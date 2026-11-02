from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework.test import APIClient

import pytest

from actions.models import Action
from actions.models.attributes import AttributeRichText, AttributeType
from actions.tests.factories import ActionFactory, AttributeTypeFactory

pytestmark = pytest.mark.django_db


def _rich_text_attribute_type(plan):
    return AttributeTypeFactory.create(
        object_content_type=ContentType.objects.get_for_model(Action),
        scope=plan,
        format=AttributeType.AttributeFormat.RICH_TEXT,
    )


def _build_attr(attribute_type, action, text: str) -> AttributeRichText:
    return AttributeRichText(
        type=attribute_type,
        content_type=ContentType.objects.get_for_model(Action),
        object_id=action.pk,
        text=text,
    )


def test_attribute_save_normalizes_bare_void_tag(plan) -> None:
    at = _rich_text_attribute_type(plan)
    action = ActionFactory.create(plan=plan)
    attr = _build_attr(at, action, '<p>a<br>b</p>')
    attr.save()
    attr.refresh_from_db()
    assert attr.text == '<p>a<br/>b</p>'


def test_attribute_save_rejects_irreparable_markup(plan) -> None:
    at = _rich_text_attribute_type(plan)
    action = ActionFactory.create(plan=plan)
    attr = _build_attr(at, action, '<p><em>crossed</p></em>')
    with pytest.raises(ValidationError):
        attr.save()


def _put_rich_text(plan, user, action, at, html: str):
    url = reverse('action-list', args=(plan.pk,))
    payload = [
        {
            'id': action.pk,
            'identifier': action.identifier,
            'name': action.name,
            'version': action.version,
            'rich_text_attributes': {at.identifier: html},
        },
    ]
    client = APIClient()
    client.raise_request_exception = False
    client.force_authenticate(user)
    return client.put(url, data=payload, format='json')


def test_rest_bulk_rich_text_attribute_is_normalized(plan, plan_admin_user) -> None:
    at = _rich_text_attribute_type(plan)
    action = ActionFactory.create(plan=plan)
    resp = _put_rich_text(plan, plan_admin_user, action, at, '<p>a<br>b</p>')
    assert resp.status_code == 200, resp.content
    attr = AttributeRichText.objects.get(
        type=at,
        content_type=ContentType.objects.get_for_model(Action),
        object_id=action.pk,
    )
    assert attr.text == '<p>a<br/>b</p>'


def test_rest_bulk_rich_text_attribute_rejects_irreparable(plan, plan_admin_user) -> None:
    at = _rich_text_attribute_type(plan)
    action = ActionFactory.create(plan=plan)
    resp = _put_rich_text(plan, plan_admin_user, action, at, '<p><em>crossed</p></em>')
    assert resp.status_code == 400, resp.content
