from django.db import models
from django.utils.translation import gettext_lazy as _
from modeltrans.fields import TranslationField


class ClientQuerySet(models.QuerySet):
    def for_request(self, request):
        hostname = request.get_host()
        if ':' in hostname:
            hostname = hostname.split(':')[0]
        return self.filter(admin_hostnames__hostname=hostname)


class Client(models.Model):
    name = models.CharField(max_length=100)
    azure_ad_tenant_id = models.CharField(max_length=200)
    login_header_text = models.CharField(verbose_name=_('login header text'), max_length=200)
    login_button_text = models.CharField(verbose_name=_('login button text'), max_length=200)

    i18n = TranslationField(fields=['login_header_text', 'login_button_text'])

    objects = ClientQuerySet.as_manager()

    def __str__(self):
        return self.name


class AdminHostname(models.Model):
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, null=False, blank=False, related_name='admin_hostnames'
    )
    hostname = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.hostname


class ClientPlan(models.Model):
    client = models.ForeignKey(
        Client, on_delete=models.CASCADE, null=False, blank=False, related_name='plans'
    )
    plan = models.ForeignKey(
        'actions.Plan', on_delete=models.CASCADE, null=False, blank=False, related_name='clients'
    )

    def __str__(self):
        return str(self.plan)
