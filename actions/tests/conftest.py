import pytest
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from actions.models import Plan, Action
from people.models import Person


User = get_user_model()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def plan():
    return Plan.objects.create(name='Test plan', identifier='test')


@pytest.fixture
def action(plan):
    action = Action(plan=plan, name='Test action 1', identifier='t1')
    action.official_name = action.name
    action.save()
    return action


@pytest.fixture
def plan_admin_user(plan):
    user = User.objects.create(
        first_name='Plan', last_name='Admin', email='plan.admin@example.com'
    )
    plan.general_admins.add(user)
    return user


@pytest.fixture
def action_contact_user(action):
    user = User.objects.create(
        first_name='Contact', last_name='Person', email='contact.person@example.com'
    )
    person = Person.objects.create(
        email=user.email, first_name=user.first_name, last_name=user.last_name
    )
    action.contact_persons.add(person)
    return user
