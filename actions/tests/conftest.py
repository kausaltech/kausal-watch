import json
import pytest
from rest_framework.test import APIClient
from django.urls import reverse
from pytest_factoryboy import register

from .factories import ActionFactory, CategoryFactory, CategoryTypeFactory, PlanFactory

register(ActionFactory)
register(CategoryFactory)
register(CategoryTypeFactory)
register(PlanFactory)
# register(UserFactory)


class JSONAPIClient(APIClient):
    def request(self, **kwargs):
        resp = super().request(**kwargs)
        resp.json_data = json.loads(resp.content)
        return resp


# @pytest.fixture
# def action_contact_user(action):
#     user = User.objects.create(
#         first_name='Contact', last_name='Person', email='contact.person@example.com'
#     )
#     person = Person.objects.create(
#         email=user.email, first_name=user.first_name, last_name=user.last_name
#     )
#     action.contact_persons.add(person)
#     return user


@pytest.fixture
def action_list_url(plan):
    return reverse('action-list', args=(plan.pk,))


@pytest.fixture
def api_client():
    return JSONAPIClient(default_format='vnd.api+json')


@pytest.fixture
def plan_list_url():
    return reverse('plan-list')


@pytest.fixture
def person_list_url():
    return reverse('person-list')
