from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.db import models
from django.utils import formats
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from wagtail.images.models import SourceImageIOError

from sentry_sdk import capture_exception

from aplans.fields import HostnameField
from aplans.utils import (
    InstancesEditableByMixin,
    InstancesVisibleForMixin,
    OrderedModel,
    PlanRelatedModel,
    PlanRelatedModelWithRevision,
)

from users.models import User

if TYPE_CHECKING:
    from kausal_common.models.types import FK

    from actions.models.plan import Plan


class Client(ClusterableModel):
    class AuthBackend(models.TextChoices):
        NONE = '', _('Only allow password login')
        # Values are social auth backend names
        AZURE_AD = 'azure_ad', _('Microsoft Azure AD')
        GOOGLE = 'google-openidconnect', _('Google')
        OKTA = 'okta-openidconnect', _('OKTA')
        ADFS = 'adfs-openidconnect', _('ADFS OpenID Connect')
        CUSTOM_ENTRA_ID = (
            settings.SINGLE_TENANT_SPECIFIC_ENTRA_BACKEND_NAME,
            settings.SINGLE_TENANT_SPECIFIC_ENTRA_BACKEND_LABEL,
        )

    name = models.CharField(
        max_length=100,
        verbose_name=_('Name'),
        help_text=_('Name of the customer organization administering the plan'),
    )
    logo = models.ForeignKey(
        'images.AplansImage',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
    # Login method can be overridden per user: If the user has a usable password, that will be used regardless.
    auth_backend = models.CharField(
        max_length=30,
        choices=AuthBackend.choices,
        blank=True,
        verbose_name=_('login method'),
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
        Client,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name='plans',
    )
    plan = ParentalKey['Plan'](
        'actions.Plan',
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name='clients',
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
        Client,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name='email_domains',
    )
    domain = HostnameField(unique=True)

    class Meta:
        ordering = ('client', 'order')

    def __str__(self):
        return self.domain


# We used to have this for defining choices of BuiltInFieldCustomization.field_name. Commented out for now because it
# does not make much sense to use choices in the first place since we can customize the fields of any model.
# def get_built_in_field_name_choices():
#     Ideally we should get the fields dynamically. Perhaps it's easier to get from ActionAdmin rather than the
#     Action model because the latter has many fields that are not relevant for BuiltInActionAttributeType due to not
#     being editable or being just technical details (e.g., i18n).
#     from actions.action_admin import ActionAdmin
#     from actions.models.action import Action
#     panels = chain(
#         ActionAdmin.basic_panels,
#         ActionAdmin.basic_related_panels,
#         ActionAdmin.basic_related_panels_general_admin,
#         ActionAdmin.progress_panels,
#         ActionAdmin.reporting_panels,
#     )
#     field_names = [panel.field_name for panel in panels if isinstance(panel, FieldPanel)]
#     # TODO: BuiltInFieldCustomization also supports other models than Action, but for now restrict ourselves to actions
#     return [(field_name, Action._meta.get_field(field_name).verbose_name) for field_name in field_names]


class BuiltInFieldCustomization(
    PlanRelatedModelWithRevision,
    InstancesEditableByMixin,
    InstancesVisibleForMixin,
):
    plan: FK[Plan] = models.ForeignKey(
        'actions.Plan',
        on_delete=models.CASCADE,
        related_name='built_in_field_customizations',
    )
    # Model of the customized field
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    # Name of the field in the model
    field_name = models.CharField(max_length=80, verbose_name=_('field'))

    help_text_override = models.TextField(verbose_name=_('help text'), blank=True)
    label_override = models.TextField(verbose_name=_('label'), blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['plan', 'content_type', 'field_name'],
                name='unique_field_customization_per_plan',
            ),
        ]

    def clean(self):
        # Note that this will only be called when saving the instance using a form, not when doing it with save(). Since
        # for now we don't have an model admin class for this model but rely on creating instances manually in the REPL,
        # we must manually trigger the validation by calling full_clean().
        model = self.content_type.model_class()
        assert model is not None
        try:
            model._meta.get_field(self.field_name)
        except FieldDoesNotExist as err:
            raise ValidationError(
                {
                    'field_name': _("%(field)s is not a valid field in the model '%(model)s'")
                    % {
                        'field': self.field_name,
                        'model': self.content_type.model,
                    }
                }
            ) from err
        return self.field_name

    def __str__(self):
        model = self.content_type.model_class()
        assert model is not None
        model_name = model._meta.verbose_name
        target_field = model._meta.get_field(self.field_name)
        if isinstance(target_field, models.Field):
            field_label = target_field.verbose_name
        else:
            # ForeignObjectRel or GenericForeignKey
            field_label = self.field_name
        return _("Field '%(field)s' in model '%(model)s' of plan '%(plan)s'") % {
            'field': field_label,
            'model': model_name,
            'plan': str(self.plan),
        }


class BaseChangeLogMessage(PlanRelatedModel):
    plan: FK[Plan] = models.ForeignKey(
        'actions.Plan',
        on_delete=models.CASCADE,
        editable=False,
        related_name='%(class)s_set',
    )
    content = models.TextField(
        verbose_name=_('content'),
        help_text=_('Please summarize the change you made. This message will be displayed publicly.'),
    )

    created_at = models.DateTimeField(
        auto_now_add=True, editable=False, verbose_name=_('created at'),
    )
    updated_at = models.DateTimeField(
        auto_now=True, editable=False, verbose_name=_('updated at'),
    )
    created_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        verbose_name=_('created by'),
        editable=False,
    )

    i18n = TranslationField(
        fields=['content'],
        default_language_field='plan__primary_language_lowercase',
    )
    content_i18n: str

    public_fields: ClassVar = [
        'id',
        'content',
        'created_at',
        'updated_at',
    ]

    class Meta:
        abstract = True
        ordering = ('-created_at',)

    def get_str_template(self):
        return _('%(verbose_name)s: "%(instance)s" (%(date)s).')

    def get_instance(self) -> models.Model:
        raise NotImplementedError()

    def __str__(self):
        verbose_name = self._meta.verbose_name or _('change history message')
        return self.get_str_template() % {
            'verbose_name': verbose_name.title(),
            'instance': self.get_instance(),
            'date': formats.date_format(self.created_at.date())
        }
