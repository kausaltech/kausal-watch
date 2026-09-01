from django.utils import translation
from django.utils.translation import get_language

import pytest

from actions.tests.factories import PlanFactory
from notifications.management.commands.initialize_notifications import initialize_notification_templates

pytestmark = pytest.mark.django_db


def test_initialize_notification_templates_does_not_leak_language():
    plan = PlanFactory.create(primary_language='fi')
    translation.activate('en')
    assert get_language() == 'en'
    initialize_notification_templates(plan_identifier=plan.identifier)
    assert get_language() == 'en'
