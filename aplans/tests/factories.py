from factory import Sequence, SubFactory
from factory.django import DjangoModelFactory

from django_orghierarchy.models import Organization, OrganizationClass


class OrganizationClassFactory(DjangoModelFactory):
    class Meta:
        model = OrganizationClass

    id = Sequence(lambda i: f'organization-class-{i}')
    name = Sequence(lambda i: f"Organization class {i}")


class OrganizationFactory(DjangoModelFactory):
    class Meta:
        model = Organization

    id = Sequence(lambda i: f'organization{i}')
    name = Sequence(lambda i: f"Organization {i}")
    abbreviation = Sequence(lambda i: f'org{i}')
    parent = None
    classification = SubFactory(OrganizationClassFactory)
