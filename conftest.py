from pytest_factoryboy import register

from actions.tests.factories import OrganizationFactory, PlanFactory

register(OrganizationFactory)
register(PlanFactory)
