from __future__ import annotations

import typing

import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains

from actions.action_admin import ActionAdmin
from actions.tests.factories import ActionContactFactory, ActionFactory, PlanFactory
from actions.wagtail_admin import ActivePlanAdmin
from admin_site.tests.factories import ClientPlanFactory
from aplans.types import WatchAdminRequest
from conftest import ModelAdminEditTest

if typing.TYPE_CHECKING:
    from users.models import User
    from people.models import Person
    from actions.models import Action

pytestmark = pytest.mark.django_db


def get_request(rf, user=None, view_name='wagtailadmin_home', url=None):
    if url is None:
        url = reverse(view_name)
    request = rf.get(url)
    if user is not None:
        request.user = user
    return request


@pytest.mark.parametrize("user__is_staff", [False])
def test_no_access_for_non_staff_user(user, client):
    client.force_login(user)
    response = client.get(reverse('wagtailadmin_home'), follow=True)
    assertContains(response, "You do not have permission to access the admin")


def test_login_removes_user_from_staff_if_no_plan_admin(user, client):
    assert user.is_staff
    assert not user.get_adminable_plans()
    client.force_login(user)
    user.refresh_from_db()
    assert not user.is_staff


def test_active_plan_menu_item_not_shown_to_action_contact_person(rf):
    action_contact = ActionContactFactory()
    request = get_request(rf, action_contact.person.user)
    active_plan_admin = ActivePlanAdmin()
    assert not active_plan_admin.get_menu_item().is_shown(request)


def test_active_plan_menu_item_shown_to_plan_admin(plan_admin_user, rf):
    request = get_request(rf, plan_admin_user)
    active_plan_admin = ActivePlanAdmin()
    assert active_plan_admin.get_menu_item().is_shown(request)


def test_active_plan_menu_item_shown_to_superuser(superuser, rf):
    request: WatchAdminRequest = get_request(rf, superuser)
    active_plan_admin = ActivePlanAdmin()
    assert active_plan_admin.get_menu_item().is_shown(request)


def test_cannot_list_plans(plan_admin_user, client):
    active_plan_admin = ActivePlanAdmin()
    url = active_plan_admin.url_helper.index_url
    client.force_login(plan_admin_user)
    response = client.get(url)
    # Wagtail doesn't respond with HTTP status 403 but with a redirect and an error message in a cookie.
    assert response.status_code == 302
    assert response.url == reverse('wagtailadmin_home')


def test_superuser_can_list_plans(superuser, plan, client):
    # If the `plan` fixture is not included, the code will fail as there would be no plan, hence no active admin plan.
    ClientPlanFactory(plan=plan)
    active_plan_admin = ActivePlanAdmin()
    url = active_plan_admin.url_helper.index_url
    client.force_login(superuser)
    response = client.get(url)
    assert response.status_code == 200


def test_cannot_access_other_plan_edit_page(plan_admin_user, client):
    other_plan = PlanFactory()
    active_plan_admin = ActivePlanAdmin()
    url = active_plan_admin.url_helper.get_action_url('edit', other_plan.pk)
    client.force_login(plan_admin_user)
    response = client.get(url)
    # Wagtail doesn't respond with HTTP status 403 but with a redirect and an error message in a cookie.
    assert response.status_code == 302
    assert response.url == reverse('wagtailadmin_home')


def test_can_access_plan_edit_page(plan_admin_user, client):
    active_plan_admin = ActivePlanAdmin()
    plan = plan_admin_user.get_adminable_plans()[0]
    ClientPlanFactory(plan=plan)
    url = active_plan_admin.url_helper.get_action_url('edit', plan.pk)
    client.force_login(plan_admin_user)
    response = client.get(url)
    assert response.status_code == 200


def test_action_admin(
    plan_admin_user: User, action_contact_person: Person, action: Action,
    test_modeladmin_edit: ModelAdminEditTest
):
    ClientPlanFactory(plan=action.plan)
    post_data = dict(name='Modified name', identifier=action.identifier)
    test_modeladmin_edit(
        ActionAdmin, action, plan_admin_user, post_data=post_data, can_inspect=True, can_edit=True
    )
    return
    # FIXME
    action.refresh_from_db()
    #assert action.name == post_data['name']
    test_modeladmin_edit(
        ActionAdmin, action, action_contact_person.user, post_data=post_data, can_inspect=True, can_edit=True
    )
    other_action = ActionFactory.create(plan=action.plan)
    test_modeladmin_edit(
        ActionAdmin, other_action, plan_admin_user, post_data=post_data, can_inspect=True, can_edit=True
    )
    test_modeladmin_edit(
        ActionAdmin, other_action, action_contact_person.user, post_data=post_data, can_inspect=True, can_edit=False
    )
