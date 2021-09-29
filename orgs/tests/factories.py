from factory import Sequence, SubFactory
from factory.django import DjangoModelFactory

from orgs.models import Namespace, Organization, OrganizationClass, OrganizationIdentifier


class NamespaceFactory(DjangoModelFactory):
    class Meta:
        model = Namespace

    identifier = Sequence(lambda i: f'namespace-{i}')
    name = Sequence(lambda i: f"Namespace {i}")


class OrganizationClassFactory(DjangoModelFactory):
    class Meta:
        model = OrganizationClass

    identifier = Sequence(lambda i: f'organization-class-{i}')
    name = Sequence(lambda i: f"Organization class {i}")


class OrganizationFactory(DjangoModelFactory):
    class Meta:
        model = Organization

    classification = SubFactory(OrganizationClassFactory)
    name = Sequence(lambda i: f"Organization {i}")
    abbreviation = Sequence(lambda i: f'org{i}')

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        parent = kwargs.pop('parent', None)
        node = Organization(*args, **kwargs)
        if parent:
            return parent.add_child(instance=node)
        return Organization.add_root(instance=node)


class OrganizationIdentifierFactory(DjangoModelFactory):
    class Meta:
        model = OrganizationIdentifier

    organization = SubFactory(OrganizationFactory)
    identifier = Sequence(lambda i: f'org{i}')
    namespace = SubFactory(NamespaceFactory)
