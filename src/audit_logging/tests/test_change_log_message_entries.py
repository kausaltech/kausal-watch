from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

import pytest

from actions.models.action import ActionChangeLogMessage, IndicatorChangeLogMessage
from actions.tests.factories import ActionFactory, PlanFactory
from actions.tests.test_change_log_graphql import make_plan_admin
from audit_logging.models import CHANGE_LOG_MESSAGE_CONTENT_KEY, PlanScopedModelLogEntry
from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory

if TYPE_CHECKING:
    from django.test import Client

    from actions.models import Action, Plan
    from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def plan() -> Plan:
    plan = PlanFactory.create()
    plan.features.enable_change_log = True
    plan.features.save()
    return plan


@pytest.fixture
def admin_user(plan: Plan) -> User:
    return make_plan_admin(plan)


@pytest.fixture
def action(plan: Plan) -> Action:
    return ActionFactory.create(plan=plan)


def entries_for(message: ActionChangeLogMessage):
    return PlanScopedModelLogEntry.objects.for_instance(message).order_by('timestamp', 'pk')


def history_results(client: Client) -> str:
    return client.get(reverse('watch-plan-history-results')).content.decode()


def test_create_edit_and_delete_entries_store_the_text(client: Client, admin_user: User, action: Action):
    client.force_login(admin_user)
    client.post(reverse('wagtailsnippets_actions_actionchangelogmessage:add'), data={'action': action.pk, 'content': 'Original'})
    message = ActionChangeLogMessage.objects.get(action=action)
    client.post(reverse('wagtailsnippets_actions_actionchangelogmessage:edit', args=[message.pk]), data={'content': 'Edited'})
    client.post(reverse('wagtailsnippets_actions_actionchangelogmessage:delete', args=[message.pk]))
    entries = list(entries_for(message))

    assert [(e.action, e.data[CHANGE_LOG_MESSAGE_CONTENT_KEY]) for e in entries] == [
        ('wagtail.create', 'Original'),
        ('wagtail.edit', 'Edited'),
        ('wagtail.delete', 'Edited'),
    ]


def test_results_show_text_as_it_was_when_logged(client: Client, admin_user: User, action: Action):
    client.force_login(admin_user)
    client.post(
        reverse('wagtailsnippets_actions_actionchangelogmessage:add'), data={'action': action.pk, 'content': 'Original text'}
    )
    message = ActionChangeLogMessage.objects.get(action=action)
    # Change the text without logging, so that only the create entry exists
    ActionChangeLogMessage.objects.filter(pk=message.pk).update(content='Changed text')

    content = history_results(client)

    assert 'Original text' in content
    assert 'Changed text' not in content
    assert 'Current text:' not in content


def test_results_fall_back_to_current_text_for_old_entries(client: Client, admin_user: User, action: Action):
    message = ActionChangeLogMessage.objects.create(action=action, plan=action.plan, content='Message text')
    PlanScopedModelLogEntry.objects.log_action(message, 'wagtail.create', user=admin_user)
    # Entries logged before the text was stored have none
    PlanScopedModelLogEntry.objects.for_instance(message).update(data={})
    client.force_login(admin_user)

    assert 'Current text: Message text' in history_results(client)


def test_results_shorten_long_text(client: Client, admin_user: User, action: Action):
    long_text = 'word ' * 100
    message = ActionChangeLogMessage.objects.create(action=action, plan=action.plan, content=long_text)
    PlanScopedModelLogEntry.objects.log_action(message, 'wagtail.create', user=admin_user)
    client.force_login(admin_user)

    content = history_results(client)

    assert long_text.strip()[:150] in content
    assert f'>{long_text}<' not in content


def test_results_show_indicator_message_text(client: Client, plan: Plan, admin_user: User):
    indicator = IndicatorFactory.create(organization=plan.organization, common=None)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    message = IndicatorChangeLogMessage.objects.create(indicator=indicator, plan=plan, content='Indicator text')
    PlanScopedModelLogEntry.objects.log_action(message, 'wagtail.create', user=admin_user)
    client.force_login(admin_user)

    assert 'Indicator text' in history_results(client)


def test_other_entries_have_no_message_text(admin_user: User, action: Action):
    entry = PlanScopedModelLogEntry.objects.log_action(action, 'wagtail.edit', user=admin_user)

    assert entry is not None
    assert CHANGE_LOG_MESSAGE_CONTENT_KEY not in entry.data


def test_results_handle_entries_of_deleted_content_types(client: Client, action: Action):
    from users.tests.factories import UserFactory

    superuser = UserFactory.create(is_superuser=True)
    message = ActionChangeLogMessage.objects.create(action=action, plan=action.plan, content='Text')
    PlanScopedModelLogEntry.objects.log_action(message, 'wagtail.create', user=superuser)
    # Wagtail keeps the entries of a deleted content type, without the content type
    PlanScopedModelLogEntry.objects.for_instance(message).update(content_type=None)
    client.force_login(superuser)

    assert client.get(reverse('watch-plan-history-results')).status_code == 200
