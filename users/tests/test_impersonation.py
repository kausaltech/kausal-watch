import pytest
from django.urls import reverse

from users.tests.factories import UserFactory


pytestmark = pytest.mark.django_db

def test_superuser_can_impersonate_and_release(client):
    superuser = UserFactory(username='superuser', is_superuser=True)
    regular_user = UserFactory(username='regular_user')
    client.force_login(superuser)
    url = reverse('hijack:acquire')
    response = client.post(url, {'user_pk': regular_user.pk})
    assert response.status_code == 302  # Redirect on success
    assert response.wsgi_request.user == regular_user  # User is impersonated

    url = reverse('hijack:release')
    response = client.post(url)
    assert response.status_code == 302  # Redirect on success
    assert response.wsgi_request.user == superuser  # User is back to own user

def test_regular_user_cannot_impersonate(client):
    regular_user = UserFactory(username='regular_user')
    another_user = UserFactory(username='another')
    client.force_login(regular_user)
    
    url = reverse('hijack:acquire')
    response = client.post(url, {'user_pk': another_user.pk})
    assert response.status_code == 403  # Forbidden
    assert response.wsgi_request.user == regular_user  # User is not impersonated


def test_superuser_cannot_impersonate_themselves(client):
    superuser = UserFactory(username='superuser', is_superuser=True)
    client.force_login(superuser)
    
    url = reverse('hijack:acquire')
    response = client.post(url, {'user_pk': superuser.pk})
    assert response.status_code == 403  # Forbidden

def test_impersonated_cannot_impersonate(client):
    superuser = UserFactory(username='superuser', is_superuser=True)
    another_superuser = UserFactory(username='another_superuser', is_superuser=True)
    regular_user = UserFactory(username='regular_user')
    client.force_login(superuser)
    
    url = reverse('hijack:acquire')
    response = client.post(url, {'user_pk': another_superuser.pk})
    assert response.status_code == 302  # Redirect on success
    assert response.wsgi_request.user == another_superuser  # User is impersonated

    response = client.post(url, {'user_pk': regular_user.pk})
    assert response.status_code == 403  # Forbidden
    assert response.wsgi_request.user == another_superuser  # User is still impersonating another_superuser

    url = reverse('hijack:release')
    response = client.post(url)
    assert response.status_code == 302  # Redirect on success
    assert response.wsgi_request.user == superuser  # User is back to own user

    url = reverse('hijack:acquire')
    response = client.post(url, {'user_pk': regular_user.pk})
    assert response.status_code == 302  # Redirect on success
    assert response.wsgi_request.user == regular_user  # Now impersonation works and user is impersonating regular_user
