import pytest

from orgs.tests.factories import OrganizationFactory
from users.tests.factories import OrganizationAdminFactory

pytestmark = pytest.mark.django_db


def test_get_adminable_organizations(user):
    organization = OrganizationFactory()
    OrganizationAdminFactory(user=user, organization=organization)
    assert list(user.get_adminable_organizations()) == [organization]


def test_get_adminable_organizations_descendants(user):
    organization = OrganizationFactory()
    OrganizationAdminFactory(user=user, organization=organization)
    sub_org = OrganizationFactory(parent=organization)
    assert list(user.get_adminable_organizations()) == [organization, sub_org]
