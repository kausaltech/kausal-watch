from django.contrib.contenttypes.models import ContentType

from factory import LazyAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory

from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin

from actions.models import Plan
from actions.tests.factories import PlanFactory
from admin_site.models import BuiltInFieldCustomization, Client, ClientPlan, EmailDomains


class EmailDomainsFactory(DjangoModelFactory[EmailDomains]):
    class Meta:
        model = 'admin_site.EmailDomains'

    client = SubFactory[EmailDomains, Client]('admin_site.tests.factories.ClientFactory')
    domain = 'example.com'


class ClientFactory(DjangoModelFactory[Client]):
    class Meta:
        model = 'admin_site.Client'

    name = Sequence(lambda i: f'Client {i}')
    auth_backend = Client.AuthBackend.AZURE_AD


class ClientPlanFactory(DjangoModelFactory[ClientPlan]):
    class Meta:
        model = 'admin_site.ClientPlan'

    client = SubFactory[ClientPlan, Client](ClientFactory)
    plan = SubFactory[ClientPlan, Plan]('actions.tests.factories.PlanFactory')


class BuiltInFieldCustomizationFactory(DjangoModelFactory[BuiltInFieldCustomization]):
    class Meta:
        model = 'admin_site.BuiltInFieldCustomization'

    plan = SubFactory[BuiltInFieldCustomization, Plan](PlanFactory)
    content_type = LazyAttribute[BuiltInFieldCustomization, ContentType](
        lambda _: ContentType.objects.get(app_label='actions', model='action')
    )
    field_name = 'identifier'
    help_text_override = 'overridden help text'
    label_override = 'overridden label'
    instances_editable_by = InstancesEditableByMixin.EditableBy.AUTHENTICATED
    instances_visible_for = InstancesVisibleForMixin.VisibleFor.PUBLIC
