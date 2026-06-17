from django.conf import settings
from django.urls import reverse

import pytest

from actions.tests.factories import ActionFactory
from indicators.tests.factories import IndicatorLevelFactory

pytestmark = pytest.mark.django_db


def test_action_change_url_is_absolute_admin_url():
    action = ActionFactory.create()
    expected = settings.ADMIN_BASE_URL + reverse('actions_action_modeladmin_edit', kwargs=dict(instance_pk=action.id))
    context = action.get_notification_context()
    assert context['change_url'] == expected
    assert context['change_url'].startswith(settings.ADMIN_BASE_URL)


def test_indicator_edit_values_url_is_absolute_admin_url():
    indicator_level = IndicatorLevelFactory.create()
    indicator = indicator_level.indicator
    plan = indicator_level.plan
    context = indicator.get_notification_context(plan)
    assert context['edit_values_url'].startswith(settings.ADMIN_BASE_URL)
