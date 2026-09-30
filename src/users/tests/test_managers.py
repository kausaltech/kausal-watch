from django.contrib.auth import authenticate

import pytest

from users.models import User
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_get_by_natural_key_ignores_case():
    user = UserFactory.create(email='First.Last@example.com')
    assert User.objects.get_by_natural_key('first.last@example.com') == user


def test_get_by_natural_key_prefers_exact_match():
    UserFactory.create(email='Same.Person@example.com')
    exact = UserFactory.create(email='same.person@example.com')
    assert User.objects.get_by_natural_key('same.person@example.com') == exact


def test_get_by_natural_key_rejects_ambiguous_case_insensitive_match():
    UserFactory.create(email='Same.Person@example.com')
    UserFactory.create(email='SAME.person@example.com')
    with pytest.raises(User.DoesNotExist):
        User.objects.get_by_natural_key('same.person@example.com')


def test_authenticate_with_lowercased_email():
    user = UserFactory.create(email='First.Last@example.com')
    assert authenticate(username='first.last@example.com', password='foobar') == user


def test_admin_login_with_differently_cased_email(client):
    user = UserFactory.create(email='First.Last@example.com')
    response = client.post('/admin/login/', {'username': 'first.last@example.com', 'password': 'foobar'})
    assert response.status_code == 302
    assert client.session['_auth_user_id'] == str(user.pk)
