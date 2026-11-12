from __future__ import annotations

from django.urls import reverse

import pytest

from actions.models.action import ActionChangeLogMessage
from actions.tests.factories import ActionFactory, PlanFactory
from admin_site.tests.factories import ClientPlanFactory
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
