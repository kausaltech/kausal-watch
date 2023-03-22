from factory import RelatedFactory, Sequence, SubFactory
from factory.django import DjangoModelFactory


class AdminHostnameFactory(DjangoModelFactory):
    class Meta:
        model = 'admin_site.AdminHostname'

    clients = SubFactory('admin_site.tests.factories.ClientFactory')
    hostname = Sequence(lambda i: f'client{i}.example.org')


class ClientFactory(DjangoModelFactory):
    class Meta:
        model = 'admin_site.Client'

    name = Sequence(lambda i: f'Client {i}')
    azure_ad_tenant_id = ''
    login_header_text = "Client login header text"
    login_button_text = "Client login button text"


class ClientPlanFactory(DjangoModelFactory):
    class Meta:
        model = 'admin_site.ClientPlan'

    client = SubFactory(ClientFactory)
    plan = SubFactory('actions.tests.factories.PlanFactory')
