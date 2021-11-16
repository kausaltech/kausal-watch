from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField

from aplans.fields import HostnameField
from aplans.utils import OrderedModel


class ClientQuerySet(models.QuerySet):
    def for_request(self, request):
        hostname = request.get_host()
        if ':' in hostname:
            hostname = hostname.split(':')[0]
        return self.filter(admin_hostnames__hostname=hostname)


class Client(ClusterableModel):
    name = models.CharField(max_length=100)
    azure_ad_tenant_id = models.CharField(max_length=200, null=True, blank=True)
    login_header_text = models.CharField(verbose_name=_('login header text'), max_length=200)
    login_button_text = models.CharField(verbose_name=_('login button text'), max_length=200)
    use_id_token_email_field = models.BooleanField(verbose_name=_('use email field of ID Token'), default=False)

    logo = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )

    i18n = TranslationField(fields=['login_header_text', 'login_button_text'])

    objects = ClientQuerySet.as_manager()

    def __str__(self):
        return self.name

    def get_admin_url(self):
        hostnames = self.admin_hostnames.all()
        if not len(hostnames):
            raise Exception('No hostnames for client %s' % self)

        return 'https://%s' % hostnames.first()


class AdminHostname(OrderedModel, ClusterableModel):
    client = ParentalKey(
        Client, on_delete=models.CASCADE, null=False, blank=False, related_name='admin_hostnames'
    )
    hostname = HostnameField(unique=True)

    class Meta:
        ordering = ('client', 'order')

    def __str__(self):
        return self.hostname


class ClientPlan(models.Model):
    client = ParentalKey(
        Client, on_delete=models.CASCADE, null=False, blank=False, related_name='plans'
    )
    plan = ParentalKey(
        'actions.Plan', on_delete=models.CASCADE, null=False, blank=False, related_name='clients'
    )

    def __str__(self):
        return str(self.plan)


class EmailDomains(OrderedModel, ClusterableModel):
    client = ParentalKey(
        Client, on_delete=models.CASCADE, null=False, blank=False, related_name='email_domains'
    )
    domain = HostnameField(unique=True)

    class Meta:
        ordering = ('client', 'order')

    def __str__(self):
        return self.domain
