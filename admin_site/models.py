from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from sentry_sdk import capture_exception
from wagtail.images.models import SourceImageIOError
from wagtail.models import DraftStateMixin, LockableMixin, RevisionMixin, WorkflowMixin

from aplans.fields import HostnameField
from aplans.utils import OrderedModel


class Client(WorkflowMixin, DraftStateMixin, LockableMixin, RevisionMixin, ClusterableModel):
    class AuthBackend(models.TextChoices):
        NONE = '', _('Only allow password login')
        # Values are social auth backend names
        AZURE_AD = 'azure_ad', _('Microsoft Azure AD')
        GOOGLE = 'google-openidconnect', _('Google')
        TUNNISTAMO = 'tunnistamo', _('Tunnistamo')

    name = models.CharField(
        max_length=100,
        verbose_name=_('Name'),
        help_text=_('Name of the customer organization administering the plan')
    )
    logo = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    # Login method can be overridden per user: If the user has a usable password, that will be used regardless.
    auth_backend = models.CharField(
        max_length=30, choices=AuthBackend.choices, blank=True, verbose_name=_("login method"),
        help_text=_("Login method that will be used for users that don't have a password set"),
    )

    def __str__(self):
        return self.name

    def get_admin_url(self):
        return settings.ADMIN_BASE_URL

    def get_notification_logo_rendition(self):
        """Return the rendition of the logo to be used for notifications, or None."""
        if self.logo is None:
            return None
        try:
            return self.logo.get_rendition('max-200x50')
        except (FileNotFoundError, SourceImageIOError) as e:
            # We ignore the error so that the query will not fail, but report it to Sentry anyway.
            capture_exception(e)
        return None

    def get_notification_logo_context(self):
        """Return the context describing the logo rendition to be used for notifications, or None."""
        rendition = self.get_notification_logo_rendition()
        if rendition:
            assert self.logo
            return {
                'url': self.get_admin_url() + rendition.url,
                'height': rendition.height,
                'width': rendition.width,
                'alt': self.logo.title,
            }
        return None


class ClientPlan(OrderedModel):
    client = ParentalKey(
        Client, on_delete=models.CASCADE, null=False, blank=False, related_name='plans'
    )
    plan = ParentalKey(
        'actions.Plan', on_delete=models.CASCADE, null=False, blank=False, related_name='clients'
    )

    def get_sort_order_max(self):
        qs = self.__class__.objects.filter(plan=self.plan)
        return qs.aggregate(models.Max(self.sort_order_field))['%s__max' % self.sort_order_field] or 0

    class Meta:
        unique_together = (('plan', 'order'),)
        ordering = ('plan', 'order')

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
