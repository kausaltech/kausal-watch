import pytest
from django.urls import reverse
from pytest_django.asserts import assertContains


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
