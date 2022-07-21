import json
import pytest
from rest_framework.test import APIClient
from django.urls import reverse
from pytest_factoryboy import register

from .factories import (
    ActionFactory, CategoryFactory, CategoryTypeFactory, CommonCategoryFactory, CommonCategoryTypeFactory,
    PlanFactory
)

register(ActionFactory)
register(CategoryFactory)
register(CategoryTypeFactory)
register(CommonCategoryFactory)
register(CommonCategoryTypeFactory)
register(PlanFactory)
# register(UserFactory)


class JSONAPIClient(APIClient):
    default_format = 'json'

    def request(self, **kwargs):
        if 'HTTP_ACCEPT' not in kwargs:
            kwargs['HTTP_ACCEPT'] = 'application/json'
        resp = super().request(**kwargs)
        resp.json_data = json.loads(resp.content)
        return resp


@pytest.fixture
def action_list_url(plan):
    return reverse('action-list', args=(plan.pk,))


@pytest.fixture
def action_detail_url(plan, action):
    return reverse('action-detail', kwargs={'plan_pk': plan.pk, 'pk': action.pk})


@pytest.fixture
def openapi_url():
    return reverse('schema')


@pytest.fixture
def api_client():
    client = JSONAPIClient()
    return client


@pytest.fixture
def plan_list_url():
    return reverse('plan-list')


@pytest.fixture
def person_list_url():
    return reverse('person-list')


@pytest.fixture
def plan_with_pages(plan):
    from actions.models.plan import set_default_page_creation

    with set_default_page_creation(True):
        plan.save()
    return plan
