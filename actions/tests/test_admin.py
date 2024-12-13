from __future__ import annotations

import typing

from django.urls import reverse

import pytest
from pytest_django.asserts import assertContains

from actions.action_admin import ActionAdmin
from actions.tests.factories import ActionFactory, PlanFactory
from actions.wagtail_admin import PlanIndexView, PlanViewSet
from admin_site.tests.factories import ClientPlanFactory

if typing.TYPE_CHECKING:
    from actions.models import Action
    from conftest import ModelAdminEditTest
    from people.models import Person
    from users.models import User

pytestmark = pytest.mark.django_db


def get_request(rf, user=None, view_name='wagtailadmin_home', url=None):
    if url is None:
        url = reverse(view_name)
    request = rf.get(url)
    if user is not None:
        request.user = user
    return request


def get_plan_index_view(rf, client, user, view_set=None) -> PlanIndexView:
    if view_set is None:
        view_set = PlanViewSet()
    client.force_login(user)
    request = get_request(rf, user)
    index_view = PlanIndexView(**view_set.get_common_view_kwargs(), **view_set.get_index_view_kwargs())
    index_view.setup(request)
    return index_view


def edit_button_shown(rf, client, user, plan) -> bool:
    view_set = PlanViewSet()
    index_view = get_plan_index_view(rf, client, user, view_set)
    buttons = index_view.get_list_buttons(user.get_active_admin_plan())
    edit_url_name = view_set.get_url_name('edit')
    return any(
        any(b.url == reverse(edit_url_name, args=[plan.pk]) for b in getattr(button, 'dropdown_buttons', []))
        for button in buttons
    )


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


def test_plan_edit_button_shown_to_superuser(rf, client, superuser, plan):
    assert edit_button_shown(rf, client, superuser, plan)


def test_plan_edit_button_shown_to_plan_admin(rf, client, plan_admin_user, plan):
    assert edit_button_shown(rf, client, plan_admin_user, plan)


def test_plan_edit_button_not_shown_to_action_contact_person(rf, client, action_contact_person_user, plan):
    assert not edit_button_shown(rf, client, action_contact_person_user, plan)


def test_superuser_can_list_plans(rf, superuser, plan, client):
    other_plan = PlanFactory()
    view_set = PlanViewSet()
    index_view = get_plan_index_view(rf, client, superuser, view_set)
    qs = index_view.get_queryset()
    assert plan in qs
    assert other_plan in qs


def test_admin_can_list_only_own_plan(rf, plan, plan_admin_user, client):
    other_plan = PlanFactory()
    view_set = PlanViewSet()
    index_view = get_plan_index_view(rf, client, plan_admin_user, view_set)
    qs = index_view.get_queryset()
    assert plan in qs
    assert other_plan not in qs


def test_can_access_plan_edit_page(plan, plan_admin_user, client):
    ClientPlanFactory(plan=plan)
    view_set = PlanViewSet()
    edit_url_name = view_set.get_url_name('edit')
    url = reverse(edit_url_name, args=[plan.pk])
    client.force_login(plan_admin_user)
    response = client.get(url)
    assert response.status_code == 200


def test_cannot_access_other_plan_edit_page(plan, plan_admin_user, client):
    other_plan = PlanFactory()
    view_set = PlanViewSet()
    edit_url_name = view_set.get_url_name('edit')
    url = reverse(edit_url_name, args=[other_plan.pk])
    client.force_login(plan_admin_user)
    response = client.get(url)
    # Wagtail doesn't respond with HTTP status 403 but with a redirect and an error message in a cookie.
    view_set.permission_policy.user_has_permission_for_instance(plan_admin_user, 'edit', plan)
    assert response.status_code == 302
    assert response.url == reverse('wagtailadmin_home')


def test_action_admin(
    plan_admin_user: User, action_contact_person: Person, action: Action,
    test_modeladmin_edit: ModelAdminEditTest,
):
    ClientPlanFactory(plan=action.plan)
    post_data = dict(name='Modified name', identifier=action.identifier)
    test_modeladmin_edit(
        ActionAdmin, action, plan_admin_user, post_data=post_data, can_inspect=True, can_edit=True,
    )
    return
    # FIXME
    action.refresh_from_db()
    #assert action.name == post_data['name']
    test_modeladmin_edit(
        ActionAdmin, action, action_contact_person.user, post_data=post_data, can_inspect=True, can_edit=True,
    )
    other_action = ActionFactory.create(plan=action.plan)
    test_modeladmin_edit(
        ActionAdmin, other_action, plan_admin_user, post_data=post_data, can_inspect=True, can_edit=True,
    )
    test_modeladmin_edit(
        ActionAdmin, other_action, action_contact_person.user, post_data=post_data, can_inspect=True, can_edit=False,
    )
