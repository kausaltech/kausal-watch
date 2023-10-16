from factory import RelatedFactory, Sequence, SubFactory
from factory.django import DjangoModelFactory
from admin_site.models import Client


class EmailDomainsFactory(DjangoModelFactory):
    class Meta:
        model = 'admin_site.EmailDomains'

    client = SubFactory('admin_site.tests.factories.ClientFactory')
    domain = 'example.com'


class ClientFactory(DjangoModelFactory):
    class Meta:
        model = 'admin_site.Client'

    name = Sequence(lambda i: f'Client {i}')
    auth_backend = Client.AuthBackend.AZURE_AD


class ClientPlanFactory(DjangoModelFactory):
    class Meta:
        model = 'admin_site.ClientPlan'

    client = SubFactory(ClientFactory)
    plan = SubFactory('actions.tests.factories.PlanFactory')
