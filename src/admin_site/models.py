from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist, ObjectDoesNotExist, ValidationError
from django.db import models
from django.utils import formats
from django.utils.translation import gettext_lazy as _, pgettext_lazy
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

from admin_site.field_customization import get_content_type_label, get_field_label, humanize_field_name
from users.models import User

if TYPE_CHECKING:
    from kausal_common.models.types import FK, RevMany

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

    email_domains: RevMany[EmailDomains]

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
    client = ParentalKey[Client](
        Client,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name='plans',
    )
    plan: FK[Plan] = ParentalKey['Plan'](
        'actions.Plan',
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        related_name='clients',
    )

    def get_sort_order_max(self):
        qs = self.__class__.objects.filter(plan=self.plan)
        return qs.aggregate(models.Max(self.sort_order_field))['%s__max' % self.sort_order_field] or 0

    def filter_siblings(self, qs: models.QuerySet[Self]) -> models.QuerySet[Self]:
        return qs.filter(client=self.client)

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

    def filter_siblings(self, qs: models.QuerySet[Self]) -> models.QuerySet[Self]:
        return qs.filter(client=self.client)

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
        verbose_name = _('field customization')
        verbose_name_plural = _('field customizations')
        ordering = ('content_type', 'field_name')
        constraints = [
            models.UniqueConstraint(
                fields=['plan', 'content_type', 'field_name'],
                name='unique_field_customization_per_plan',
            ),
        ]

    @classmethod
    def get_field_access(
        cls,
        user: User,
        plan: Plan,
        model: type[models.Model],
        field_name: str,
        instance: models.Model | None,
    ) -> tuple[bool, bool]:
        """
        Return `(is_visible, is_editable)` for a built-in field of `model` in `plan`.

        Both default to True if there is no customization for the field. The values are returned as
        they are; it is up to the caller to decide whether editability should imply visibility. Note
        that `instances_editable_by` defaults to "authenticated", so a caller that lets editability
        imply visibility will effectively ignore a restricted `instances_visible_for`.
        """
        try:
            customization = cls.objects.get(
                plan=plan,
                content_type=ContentType.objects.get_for_model(model),
                field_name=field_name,
            )
        except cls.DoesNotExist:
            return (True, True)
        return (
            customization.is_instance_visible_for(user, plan, instance),
            customization.is_instance_editable_by(user, plan, instance),
        )

    def clean(self):
        # Note that this will only be called when saving the instance using a form, not when doing it with save(). When
        # creating instances programmatically (e.g., in the REPL), we must trigger the validation by calling
        # full_clean() ourselves.
        try:
            content_type = self.content_type
        except ObjectDoesNotExist:
            # No model chosen yet; the missing value is reported by the field-level validation.
            return
        if not self.field_name:
            return
        model = content_type.model_class()
        if model is None:
            raise ValidationError({
                'content_type': _("The model '%(model)s' does not exist any more") % {'model': str(content_type)}
            })
        try:
            model._meta.get_field(self.field_name)
        except FieldDoesNotExist as err:
            raise ValidationError({
                'field_name': _("%(field)s is not a valid field in the model '%(model)s'")
                % {
                    'field': self.field_name,
                    'model': content_type.model,
                }
            }) from err

    @property
    def content_type_label(self) -> str:
        """Return the human-readable label of the customized model."""
        return get_content_type_label(self.content_type)

    @property
    def field_label(self) -> str:
        """
        Return the human-readable label of the customized field.

        Degrades to the bare field name when the model itself is gone, so that a customization
        pointing at a stale content type stays listable and can be deleted.
        """
        model = self.content_type.model_class()
        if model is None:
            return humanize_field_name(self.field_name)
        return get_field_label(model, self.field_name)

    def __str__(self):
        model = self.content_type.model_class()
        model_name = model._meta.verbose_name if model is not None else str(self.content_type)
        return _("Field '%(field)s' in model '%(model)s' of plan '%(plan)s'") % {
            'field': self.field_label,
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
        auto_now_add=True,
        editable=False,
        verbose_name=_('created at'),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
        verbose_name=_('updated at'),
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
        return pgettext_lazy('change log message', '%(verbose_name)s: "%(instance)s" (%(date)s).')

    def get_instance(self) -> models.Model:
        raise NotImplementedError()

    def __str__(self):
        verbose_name = self._meta.verbose_name or _('change history message')
        return self.get_str_template() % {
            'verbose_name': verbose_name.title(),
            'instance': self.get_instance(),
            'date': formats.date_format(self.created_at.date()),
        }
