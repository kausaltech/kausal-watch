from factory import LazyAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory
from admin_site.models import Client
from django.contrib.contenttypes.models import ContentType

from actions.tests.factories import PlanFactory
from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin


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


class BuiltInFieldCustomizationFactory(DjangoModelFactory):
    class Meta:
        model = 'admin_site.BuiltInFieldCustomization'

    plan = SubFactory(PlanFactory)
    content_type = LazyAttribute(lambda _: ContentType.objects.get(app_label='actions', model='action'))
    field_name = 'identifier'
    help_text_override = 'overridden help text'
    label_override = 'overridden label'
    instances_editable_by = InstancesEditableByMixin.EditableBy.AUTHENTICATED
    instances_visible_for = InstancesVisibleForMixin.VisibleFor.PUBLIC
