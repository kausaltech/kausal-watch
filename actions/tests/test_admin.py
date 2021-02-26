import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains

from actions.wagtail_admin import ActivePlanAdmin


def get_request_home(rf, user=None):
    request = rf.get(reverse('wagtailadmin_home'))
    if user is not None:
        request.user = user
    return request


@pytest.mark.django_db
@pytest.mark.parametrize("user__is_staff", [False])
def test_no_access_for_non_staff_user(user, client):
    client.force_login(user)
    response = client.get(reverse('wagtailadmin_home'), follow=True)
    assertContains(response, "You do not have permission to access the admin")


@pytest.mark.django_db
def test_login_removes_user_from_staff_if_no_plan_admin(user, client):
    assert user.is_staff
    assert not user.get_adminable_plans()
    client.force_login(user)
    user.refresh_from_db()
    assert not user.is_staff


@pytest.mark.django_db
def test_active_plan_menu_item_not_shown_to_action_contact_person(action_contact_person, rf):
    request = get_request_home(rf, action_contact_person.user)
    active_plan_admin = ActivePlanAdmin()
    assert not active_plan_admin.get_menu_item().is_shown(request)


@pytest.mark.django_db
def test_active_plan_menu_item_shown_to_plan_admin(plan_admin_user, rf):
    request = get_request_home(rf, plan_admin_user)
    active_plan_admin = ActivePlanAdmin()
    assert active_plan_admin.get_menu_item().is_shown(request)


@pytest.mark.django_db
def test_active_plan_menu_item_shown_to_superuser(superuser, rf):
    request = get_request_home(rf, superuser)
    active_plan_admin = ActivePlanAdmin()
    assert active_plan_admin.get_menu_item().is_shown(request)

# TODO: Check that users can neither edit other plans nor list plans
