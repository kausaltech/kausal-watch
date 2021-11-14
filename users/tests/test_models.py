import pytest

from orgs.tests.factories import OrganizationFactory

pytestmark = pytest.mark.django_db


def test_get_adminable_organizations_superuser(superuser):
    organization = OrganizationFactory()
    assert list(superuser.get_adminable_organizations()) == [organization]


def test_get_adminable_organizations_is_not_admin(user):
    OrganizationFactory()
    assert list(user.get_adminable_organizations()) == []


def test_get_adminable_organizations_descendants(superuser):
    organization = OrganizationFactory()
    sub_org = OrganizationFactory(parent=organization)
    assert list(superuser.get_adminable_organizations()) == [organization, sub_org]
