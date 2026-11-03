"""The attribute type admin views."""

from __future__ import annotations

from django.contrib.contenttypes.models import ContentType

import pytest

from actions.models import Action, AttributeType, AttributeTypeChoiceOption
from actions.tests.factories import (
    ActionFactory,
    AttributeChoiceFactory,
    AttributeTypeChoiceOptionFactory,
    AttributeTypeFactory,
)
from admin_site.tests.factories import ClientPlanFactory
from admin_site.tests.utils import post_data

pytestmark = pytest.mark.django_db

TYPES_PATH = '/admin/actions/attributetype/'


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


def _action_type(plan, **kwargs) -> AttributeType:
    return AttributeTypeFactory.create(object_content_type=ContentType.objects.get_for_model(Action), scope=plan, **kwargs)


def test_deleting_used_choice_option_archives_it(admin_client, plan_with_pages):
    attribute_type = _action_type(plan_with_pages, format=AttributeType.AttributeFormat.ORDERED_CHOICE)
    used = AttributeTypeChoiceOptionFactory.create(type=attribute_type, name='Used')
    kept = AttributeTypeChoiceOptionFactory.create(type=attribute_type, name='Kept')
    AttributeChoiceFactory.create(type=attribute_type, content_object=ActionFactory.create(plan=plan_with_pages), choice=used)
    path = f'{TYPES_PATH}edit/{attribute_type.pk}/'
    data = post_data(admin_client.get(path).context['form'])
    data['choice_options-0-DELETE'] = 'on'
    response = admin_client.post(path, data, follow=True)
    used.refresh_from_db()
    assert not used.is_active
    assert AttributeTypeChoiceOption.objects.filter(pk=kept.pk, is_active=True).exists()
    assert any("'Used'" in str(message) for message in response.context['messages'])
