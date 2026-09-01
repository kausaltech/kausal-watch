from wagtail.rich_text import RichText

from factory.declarations import Sequence, SubFactory
from factory.django import DjangoModelFactory

from aplans.factories import ModelFactory

from actions.models import Plan
from orgs.models import Namespace, Organization, OrganizationClass, OrganizationIdentifier, OrganizationPlanAdmin
from people.models import Person
from people.tests.factories import PersonFactory


class NamespaceFactory(DjangoModelFactory['Namespace']):
    class Meta:
        model = Namespace

    identifier = Sequence(lambda i: f'namespace-{i}')
    name = Sequence(lambda i: f'Namespace {i}')


class OrganizationClassFactory(DjangoModelFactory['OrganizationClass']):
    class Meta:
        model = OrganizationClass

    identifier = Sequence(lambda i: f'organization-class-{i}')
    name = Sequence(lambda i: f'Organization class {i}')


class OrganizationFactory(ModelFactory[Organization]):
    class Meta:
        model = Organization

    classification = SubFactory[Organization, OrganizationClass](OrganizationClassFactory)
    name = Sequence(lambda i: f'Organization {i}')
    abbreviation = Sequence(lambda i: f'org{i}')
    primary_language = 'en'
    description = RichText('<p>Description</p>')
    url = 'https://example.org'

    @classmethod
    def _create(cls, model_class, *args, **kwargs) -> Organization:  # noqa: ARG003
        parent = kwargs.pop('parent', None)
        node = Organization(*args, **kwargs)  # type: ignore[misc]
        if parent:
            return parent.add_child(instance=node)
        return Organization.add_root(instance=node)


class OrganizationIdentifierFactory(DjangoModelFactory['OrganizationIdentifier']):
    class Meta:
        model = OrganizationIdentifier

    organization = SubFactory[OrganizationIdentifier, Organization](OrganizationFactory)
    identifier = Sequence(lambda i: f'org{i}')
    namespace = SubFactory[OrganizationIdentifier, Namespace](NamespaceFactory)


class OrganizationPlanAdminFactory(DjangoModelFactory['OrganizationPlanAdmin']):
    class Meta:
        model = OrganizationPlanAdmin

    organization = SubFactory[OrganizationPlanAdmin, Organization](OrganizationFactory)
    plan = SubFactory[OrganizationPlanAdmin, Plan]('actions.tests.factories.PlanFactory')
    person = SubFactory[OrganizationPlanAdmin, Person](PersonFactory)
