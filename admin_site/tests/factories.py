from factory import RelatedFactory, Sequence, SubFactory
from factory.django import DjangoModelFactory
from admin_site.models import Client


class EmailDomainsFactory(DjangoModelFactory):
    class Meta:
        model = 'admin_site.EmailDomains'

    client = SubFactory('admin_site.tests.factories.ClientFactory')
    domain = 'example.com'


class AdminHostnameFactory(DjangoModelFactory):
    class Meta:
        model = 'admin_site.AdminHostname'

    client = SubFactory('admin_site.tests.factories.ClientFactory')
    hostname = Sequence(lambda i: f'client{i}.example.org')


class ClientFactory(DjangoModelFactory):
    class Meta:
        model = 'admin_site.Client'

    name = Sequence(lambda i: f'Client {i}')
    admin_hostnames = RelatedFactory(AdminHostnameFactory, factory_related_name='client')
    auth_backend = Client.AuthBackend.AZURE_AD


class ClientPlanFactory(DjangoModelFactory):
    class Meta:
        model = 'admin_site.ClientPlan'

    client = SubFactory(ClientFactory)
    plan = SubFactory('actions.tests.factories.PlanFactory')
