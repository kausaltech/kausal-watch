import pytest
from django.test.client import Client
from pytest_factoryboy import register

from actions.tests.factories import OrganizationFactory, PlanFactory, UserFactory

register(OrganizationFactory)
register(PlanFactory)
register(UserFactory)


@pytest.fixture
def client():
    return Client()
