from __future__ import annotations

from typing import Any

from django.urls import reverse

import pytest

from actions.models.action import ActionChangeLogMessage
from actions.tests.factories import ActionFactory, PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from admin_site.viewsets import WatchIndexView
from audit_logging.models import PlanScopedModelLogEntry
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def action():
    plan = PlanFactory.create()
    plan.features.enable_change_log = True
    plan.features.save()
    ClientPlanFactory.create(plan=plan)
    return ActionFactory.create(plan=plan)


@pytest.fixture
def plan_admin(action):
    user = UserFactory.create()
    PersonFactory.create(user=user, general_admin_plans=[action.plan])
    return user


def has_side_panel(response) -> bool:
    return bool(list(response.context['side_panels'])) or 'data-side-panel' in response.content.decode()


def test_create_form_has_no_side_panel(client, action, plan_admin):
    client.force_login(plan_admin)

    response = client.get(reverse('wagtailsnippets_actions_actionchangelogmessage:add') + f'?action={action.pk}')

    assert response.status_code == 200
    assert not has_side_panel(response)


def test_edit_form_has_no_side_panel(client, action, plan_admin):
    message = ActionChangeLogMessage.objects.create(action=action, plan=action.plan, content='Changed', created_by=plan_admin)
    client.force_login(plan_admin)

    response = client.get(reverse('wagtailsnippets_actions_actionchangelogmessage:edit', args=[message.pk]))

    assert response.status_code == 200
    assert not has_side_panel(response)


def test_listing_annotates_last_update_from_plan_scoped_log_entries(action, plan_admin):
    """
    Wagtail's listing orders by the latest log entry, but only finds it for its own log model.

    Plan-related models are logged to `PlanScopedModelLogEntry`, so their listings failed.
    """
    message = ActionChangeLogMessage.objects.create(action=action, plan=action.plan, content='Changed', created_by=plan_admin)
    entry = PlanScopedModelLogEntry.objects.log_action(message, 'wagtail.create', user=plan_admin)
    assert entry is not None

    view = WatchIndexView[ActionChangeLogMessage](model=ActionChangeLogMessage)
    queryset = view._annotate_queryset_updated_at(ActionChangeLogMessage.objects.all())

    # An annotation, which the type checker doesn't know about
    annotated: Any = queryset.get(pk=message.pk)
    assert annotated._updated_at == entry.timestamp


@pytest.mark.parametrize('model_name', ['actionchangelogmessage', 'indicatorchangelogmessage', 'categorychangelogmessage'])
def test_message_listing_redirects_to_dashboard(client, plan_admin, model_name):
    """The messages are listed on the edit page of their object, so their own listing is not offered."""
    client.force_login(plan_admin)

    response = client.get(reverse(f'wagtailsnippets_actions_{model_name}:list'))

    assert response['Location'] == reverse('wagtailadmin_home')


def test_message_pages_lead_back_to_the_action_instead_of_the_listing(client, action, plan_admin):
    message = ActionChangeLogMessage.objects.create(action=action, plan=action.plan, content='Changed', created_by=plan_admin)
    PlanScopedModelLogEntry.objects.log_action(message, 'wagtail.create', user=plan_admin)
    client.force_login(plan_admin)
    listing_url = reverse('wagtailsnippets_actions_actionchangelogmessage:list')
    action_url = reverse('wagtailsnippets_actions_action:edit', args=[action.pk])
    pages = [
        reverse('wagtailsnippets_actions_actionchangelogmessage:add') + f'?action={action.pk}',
        reverse('wagtailsnippets_actions_actionchangelogmessage:edit', args=[message.pk]),
        reverse('wagtailsnippets_actions_actionchangelogmessage:history', args=[message.pk]),
    ]

    for url in pages:
        response = client.get(url)
        assert response.status_code == 200, url
        breadcrumbs = response.context['breadcrumbs_items']
        assert listing_url not in [item['url'] for item in breadcrumbs], url
        assert {'url': action_url, 'label': str(action)} in breadcrumbs, url


def test_deleting_without_next_returns_to_the_action(client, action, plan_admin):
    """Deleting from the message's own edit page, which passes no `next`, returns to the message's action."""
    message = ActionChangeLogMessage.objects.create(action=action, plan=action.plan, content='Changed', created_by=plan_admin)
    client.force_login(plan_admin)

    response = client.post(reverse('wagtailsnippets_actions_actionchangelogmessage:delete', args=[message.pk]))

    assert response['Location'] == reverse('wagtailsnippets_actions_action:edit', args=[action.pk])
    assert not ActionChangeLogMessage.objects.filter(pk=message.pk).exists()
