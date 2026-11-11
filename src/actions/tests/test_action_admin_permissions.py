"""Who can list, create, edit and delete actions in the admin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import NoReverseMatch, reverse

import pytest

from actions.action_admin import DISABLED_URL_NAMES
from actions.models import Action
from actions.tests import action_admin_helpers as h
from actions.tests.factories import ActionFactory, PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from admin_site.tests.utils import post_data
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.test import Client

    from actions.models import Plan
    from users.models import User

pytestmark = pytest.mark.django_db

type UserMaker = Callable[[Action], User]

ROLES: dict[str, UserMaker] = {
    'superuser': h.superuser_for,
    'plan_admin': h.plan_admin_for,
    'editor': h.make_contact_person,
    'moderator': h.make_moderator,
    'organization_admin': h.make_organization_admin,
    # Roles that give no access to the action itself
    'contact_person_of_another_action': lambda action: h.make_contact_person(ActionFactory.create(plan=action.plan)),
    'admin_of_another_plan': lambda _action: h.make_plan_admin(PlanFactory.create()),
}
ADMIN_ROLES = ['superuser', 'plan_admin']
EDITING_ROLES = [*ADMIN_ROLES, 'editor', 'moderator', 'organization_admin']
OUTSIDER_ROLES = ['contact_person_of_another_action', 'admin_of_another_plan']


@pytest.fixture(params=[False, True], ids=['without_moderation', 'with_moderation'])
def plan(request) -> Plan:
    plan = PlanFactory.create()
    if request.param:
        h.enable_moderation(plan)
    return plan


@pytest.fixture
def action(plan: Plan) -> Action:
    return ActionFactory.create(plan=plan)


def can_open(client: Client, user: User, url: str) -> bool:
    client.force_login(user)
    response = client.get(url, follow=True)
    return response.status_code == 200 and response.request['PATH_INFO'] == url


def test_anonymous_user_is_sent_to_login(client, action):
    for url in (h.index_url(), h.create_url(), h.edit_url(action), h.delete_url(action)):
        response = client.get(url)
        assert response.status_code == 302
        assert '/login' in response['Location']


def test_user_without_a_role_cannot_open_the_admin(client, action):
    user = UserFactory.create()
    PersonFactory.create(user=user)
    assert not can_open(client, user, h.index_url())
    assert not can_open(client, user, h.edit_url(action))


@pytest.mark.parametrize('role', list(ROLES))
def test_everyone_with_a_role_can_open_the_listing(client, action, role):
    assert can_open(client, ROLES[role](action), h.index_url())


@pytest.mark.parametrize(('role', 'allowed'), [(role, role in [*ADMIN_ROLES, 'admin_of_another_plan']) for role in ROLES])
def test_who_can_open_the_create_form(client, action, role, allowed):
    assert can_open(client, ROLES[role](action), h.create_url()) is allowed


@pytest.mark.parametrize('role', ADMIN_ROLES)
def test_admin_creates_an_action_in_the_active_plan(client, plan, action, role):
    user = ROLES[role](action)
    client.force_login(user)
    data = post_data(client.get(h.create_url()).context['form'])
    data.update(name='Created action', identifier='created-1')

    response = client.post(h.create_url(), data=data)

    assert response.status_code == 302
    assert Action.objects.get(name='Created action').plan == plan


def test_contact_person_cannot_create_by_posting(client, action):
    admin = h.make_plan_admin(action.plan)
    client.force_login(admin)
    data = post_data(client.get(h.create_url()).context['form'])
    data.update(name='Created action', identifier='created-1')

    client.force_login(h.make_contact_person(action))
    client.post(h.create_url(), data=data)

    assert not Action.objects.filter(name='Created action').exists()


@pytest.mark.parametrize(('role', 'allowed'), [(role, role in EDITING_ROLES) for role in ROLES])
def test_who_can_open_the_edit_form(client, action, role, allowed):
    assert can_open(client, ROLES[role](action), h.edit_url(action)) is allowed


@pytest.mark.parametrize('role', OUTSIDER_ROLES)
def test_outsider_cannot_edit_by_posting(client, action, role):
    data = h.unchanged_post_data(client, h.make_plan_admin(action.plan), action)
    data['name'] = 'Changed by an outsider'

    client.force_login(ROLES[role](action))
    client.post(h.edit_url(action), data=data)

    action.refresh_from_db()
    assert action.name != 'Changed by an outsider'
    assert action.latest_revision is None


def test_admin_of_two_plans_is_asked_to_switch_plan_for_an_action_of_the_other_one(client, action):
    other_plan = PlanFactory.create()
    ClientPlanFactory.create(plan=other_plan)
    ClientPlanFactory.create(plan=action.plan)
    user = UserFactory.create(selected_admin_plan=other_plan)
    PersonFactory.create(user=user, general_admin_plans=[action.plan, other_plan])
    client.force_login(user)

    response = client.get(h.edit_url(action))

    assert response.status_code == 302
    assert f'/change-admin-plan/{action.plan.pk}/' in response['Location']
    assert can_open(client, user, h.edit_url(action))
    user.refresh_from_db()
    assert user.selected_admin_plan == action.plan


@pytest.mark.parametrize(('role', 'allowed'), [(role, role in ADMIN_ROLES) for role in EDITING_ROLES])
def test_only_admins_can_edit_a_merged_action(client, action, role, allowed):
    user = ROLES[role](action)
    action.merged_with = ActionFactory.create(plan=action.plan)
    action.save(update_fields=['merged_with'])

    assert can_open(client, user, h.edit_url(action)) is allowed


@pytest.mark.parametrize(('role', 'allowed'), [(role, role in ADMIN_ROLES) for role in ROLES])
def test_who_can_open_the_delete_confirmation(client, action, role, allowed):
    assert can_open(client, ROLES[role](action), h.delete_url(action)) is allowed


@pytest.mark.parametrize(('role', 'allowed'), [(role, role in ADMIN_ROLES) for role in ROLES])
def test_who_can_delete_by_posting(client, action, role, allowed):
    client.force_login(ROLES[role](action))

    client.post(h.delete_url(action))

    assert Action.objects.filter(pk=action.pk).exists() is not allowed


@pytest.mark.parametrize('role', ADMIN_ROLES)
def test_locked_actions_can_be_edited_but_not_created_or_deleted(client, plan, action, role):
    user = ROLES[role](action)
    plan.actions_locked = True
    plan.save(update_fields=['actions_locked'])

    assert can_open(client, user, h.edit_url(action))
    assert not can_open(client, user, h.create_url())
    assert not can_open(client, user, h.delete_url(action))
    client.post(h.delete_url(action))
    assert Action.objects.filter(pk=action.pk).exists()


@pytest.mark.parametrize('role', ADMIN_ROLES)
def test_admin_can_open_usage_and_unpublish(client, action, role):
    user = ROLES[role](action)

    assert can_open(client, user, h.usage_url(action))
    assert can_open(client, user, h.unpublish_url(action))


@pytest.mark.parametrize('role', OUTSIDER_ROLES)
def test_outsider_cannot_open_usage_or_history(client, action, role):
    user = ROLES[role](action)

    assert not can_open(client, user, h.usage_url(action))
    assert not can_open(client, user, h.history_url(action))


@pytest.mark.parametrize('view_name', sorted(DISABLED_URL_NAMES))
def test_views_not_offered_for_actions_have_no_url(view_name):
    with pytest.raises(NoReverseMatch):
        reverse(f'wagtailsnippets_actions_action:{view_name}', args=[1])
