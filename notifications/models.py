from __future__ import annotations

import datetime
import logging
import typing
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import pgettext_lazy, gettext_lazy as _
from enum import Enum
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from typing import Dict, Sequence
from wagtail.core.fields import RichTextField

from aplans.utils import PlanRelatedModel
from people.models import Person

if typing.TYPE_CHECKING:
    from .recipients import EmailRecipient, NotificationRecipient

DEFAULT_FONT_FAMILY = (
    '-apple-system, BlinkMacSystemFont, avenir next, avenir, segoe ui, helvetica neue, helvetica, '
    'Ubuntu, roboto, noto, arial, sans-serif'
)
DEFAULT_LANG = settings.LANGUAGES[0][0]
logger = logging.getLogger('aplans.notifications')


class NotificationType(Enum):
    TASK_LATE = _("Task is late")
    TASK_DUE_SOON = _("Task is due soon")
    ACTION_NOT_UPDATED = _("Action metadata has not been updated recently")
    NOT_ENOUGH_TASKS = _("Action doesn't have enough in-progress tasks")
    UPDATED_INDICATOR_VALUES_LATE = _("Updated indicator values are late")
    UPDATED_INDICATOR_VALUES_DUE_SOON = _("Updated indicator values are due soon")
    USER_FEEDBACK_RECEIVED = _("User feedback received")

    @property
    def identifier(self):
        return self.name.lower()

    @property
    def verbose_name(self):
        return self.value

ACTION_NOTIFICATION_TYPES = {
    NotificationType.TASK_LATE,
    NotificationType.TASK_DUE_SOON,
    NotificationType.ACTION_NOT_UPDATED,
    NotificationType.NOT_ENOUGH_TASKS,
}

INDICATOR_NOTIFICATION_TYPES = {
    NotificationType.UPDATED_INDICATOR_VALUES_LATE,
    NotificationType.UPDATED_INDICATOR_VALUES_DUE_SOON,
}


def notification_type_choice_builder():
    for val in NotificationType:
        yield (val.identifier, val.verbose_name)


class NotificationSettings(ClusterableModel, PlanRelatedModel):
    plan = models.OneToOneField(
        'actions.Plan', on_delete=models.CASCADE, related_name='notification_settings',
        verbose_name=_('plan'),
    )
    notifications_enabled = models.BooleanField(
        default=False, verbose_name=_('notifications enabled'), help_text=_('Should notifications be sent?'),
    )
    send_at_time = models.TimeField(
        default=datetime.time(9, 0), verbose_name=_('notification sending time'),
        help_text=_('The local time of day when notifications are sent')
    )

    verbose_name_partitive = pgettext_lazy('partitive', 'notification settings')

    class Meta:
        verbose_name = _('notification settings')
        verbose_name_plural = _('notification settings')

    def __str__(self):
        return str(self.plan)


class SentNotificationQuerySet(models.QuerySet):
    def recipient(self, recipient: NotificationRecipient):
        return recipient.filter_sent_notifications(self)


class SentNotification(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    sent_at = models.DateTimeField()
    type = models.CharField(
        verbose_name=_('type'), choices=notification_type_choice_builder(),
        max_length=100
    )
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='notifications', blank=True, null=True)
    email = models.EmailField(
        blank=True,
        help_text=_('Set if the notification was sent to an email address instead of a person'),
    )

    objects = SentNotificationQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=((Q(person__isnull=True) & ~Q(email='')) | (Q(person__isnull=False) & Q(email=''))),
                name='person_xor_email',
           )
        ]

    def __str__(self):
        return '%s: %s -> %s' % (self.content_object, self.type, self.person)


class BaseTemplateManager(models.Manager):
    def get_by_natural_key(self, plan_identifier):
        return self.get(plan__identifier=plan_identifier)


class IndirectPlanRelatedModel(PlanRelatedModel):
    @classmethod
    def filter_by_plan(cls, plan, qs):
        return qs.filter(base__plan=plan)


class BaseTemplate(ClusterableModel, PlanRelatedModel):
    plan = models.OneToOneField(
        'actions.Plan', on_delete=models.CASCADE, related_name='notification_base_template',
        verbose_name=_('plan'),
    )
    from_name = models.CharField(verbose_name=_('Email From name'), null=True, blank=True, max_length=200)
    from_address = models.EmailField(verbose_name=_('Email From address'), null=True, blank=True)
    reply_to = models.CharField(verbose_name=_('Email Reply-To address'), null=True, blank=True, max_length=200)

    brand_dark_color = models.CharField(verbose_name=_('Brand dark color'), null=True, blank=True, max_length=30)
    logo = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    font_family = models.CharField(verbose_name=_('Font family'), null=True, blank=True, max_length=200,
                                   help_text=_('Leave empty unless custom font required by customer'))
    font_css_url = models.URLField(verbose_name=_('Font CSS style URL'), null=True, blank=True,
                                   help_text=_('Leave empty unless custom font required by customer'))

    objects = BaseTemplateManager()

    verbose_name_partitive = pgettext_lazy('partitive', 'base templates')

    class Meta:
        verbose_name = _('base template')
        verbose_name_plural = _('base templates')

    def __str__(self):
        return str(self.plan)

    def natural_key(self):
        return (self.plan.identifier,)

    def _get_font_family_with_fallback(self):
        font_family = self.font_family
        if font_family is None or len(font_family) == 0:
            return DEFAULT_FONT_FAMILY
        return f'{font_family}, {DEFAULT_FONT_FAMILY}'

    def get_notification_context(self):
        return dict(theme=dict(
            brand_dark_color=self.brand_dark_color,
            font_family=self.font_family,
            font_family_with_fallback=self._get_font_family_with_fallback(),
            font_css_url=self.font_css_url,
            link_in_brand_bg_color="#ffffff"
        ))


class NotificationTemplateManager(models.Manager):
    def get_by_natural_key(self, base, type_):
        return self.get(base__plan__identifier=base[0], type=type_)


class NotificationTemplate(models.Model, IndirectPlanRelatedModel):
    base = ParentalKey(BaseTemplate, on_delete=models.CASCADE, related_name='templates', editable=False)
    subject = models.CharField(
        verbose_name=_('subject'), max_length=200, help_text=_('Subject for email notifications')
    )
    type = models.CharField(
        verbose_name=_('type'), choices=notification_type_choice_builder(),
        max_length=100,
    )
    custom_email = models.EmailField(
        blank=True, verbose_name=_('custom email address'),
        help_text=_('Email address used when "send to custom email address" is checked'),
    )
    send_to_plan_admins = models.BooleanField(verbose_name=_('send to plan admins'), default=True)
    send_to_custom_email = models.BooleanField(verbose_name=_('send to custom email address'), default=False)

    class ContactPersonFallbackChain(models.TextChoices):
        DO_NOT_SEND = '', _('Do not send to contact persons')
        CONTACT_PERSONS = 'cp', _('Send to contact persons')
        CONTACT_PERSONS_THEN_ORG_ADMINS = 'cp-oa', _('Send to contact persons; fallback: organization admins')
        CONTACT_PERSONS_THEN_ORG_ADMINS_THEN_PLAN_ADMINS = 'cp-oa-pa', _('Send to contact persons; fallback: organization admins, plan admins')

    send_to_contact_persons = models.CharField(
        max_length=50, verbose_name=_('send to contact persons'), blank=True,
        choices=ContactPersonFallbackChain.choices,
    )

    objects = NotificationTemplateManager()

    class Meta:
        ordering = ('type', 'subject')
        verbose_name = _('notification template')
        verbose_name_plural = _('notification templates')
        unique_together = (('base', 'type'),)
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(custom_email='') & Q(send_to_custom_email=False))
                    | (~Q(custom_email='') & Q(send_to_custom_email=True))
                ),
                name='custom_email_iff_send_to_custom_email',
           )
        ]


    def __str__(self):
        for val in NotificationType:
            if val.identifier == self.type:
                return str(val.verbose_name)
        return 'N/A'

    def natural_key(self):
        return (self.base.natural_key(), self.type)
    natural_key.dependencies = ['notifications.BaseTemplate']

    def clean(self):
        if not self.custom_email and self.send_to_custom_email:
            raise ValidationError({
                'send_to_custom_email': _('This can only be set if a custom email address is defined')
            })
        if self.custom_email and not self.send_to_custom_email:
            raise ValidationError({
                'send_to_custom_email': _('If a custom email address is defined, this must be set')
            })
        if self.send_to_contact_persons and not self.concerns_action and not self.concerns_indicator:
            raise ValidationError({
                'send_to_contact_persons': _('Notifications of this type cannot be sent to contact persons')
            })

    @property
    def concerns_action(self):
        return self.type in (t.identifier for t in ACTION_NOTIFICATION_TYPES)

    @property
    def concerns_indicator(self):
        return self.type in (t.identifier for t in INDICATOR_NOTIFICATION_TYPES)

    def get_recipients(
        self, action_contacts: Dict[int, Sequence[NotificationRecipient]],
        indicator_contacts: Dict[int, Sequence[NotificationRecipient]], plan_admins: Sequence[NotificationRecipient],
        organization_plan_admins: Dict[int, Sequence[NotificationRecipient]], action=None, indicator=None,
    ) -> Sequence[NotificationRecipient]:
        recipients = []
        if self.send_to_plan_admins:
            recipients += plan_admins
        if self.send_to_custom_email:
            recipient = self.get_email_recipient()
            if not recipient:
                raise Exception(f'There is no custom email recipient for notifications of type {self.type}')
            recipients += [recipient]
        if self.send_to_contact_persons:
            recipients += self._get_contact_person_recipients(
                action_contacts, indicator_contacts, organization_plan_admins, plan_admins, action, indicator
            )
        return recipients

    def _get_contact_person_recipients(
        self, action_contacts, indicator_contacts, organization_plan_admins, plan_admins, action, indicator
    ):
        recipients = []
        fall_back_to_org_admins = (
            self.send_to_contact_persons == self.ContactPersonFallbackChain.CONTACT_PERSONS_THEN_ORG_ADMINS
            or self.send_to_contact_persons == self.ContactPersonFallbackChain.CONTACT_PERSONS_THEN_ORG_ADMINS_THEN_PLAN_ADMINS
        )
        fall_back_to_plan_admins = (
            self.send_to_contact_persons == self.ContactPersonFallbackChain.CONTACT_PERSONS_THEN_ORG_ADMINS_THEN_PLAN_ADMINS
        )

        if self.concerns_action:
            if not action:
                raise Exception(f'Notifications of type {self.type} must refer to an action')
            recipients += action_contacts.get(action.id, [])
            if not recipients:
                if fall_back_to_org_admins:
                    org_ids = set((p.organization_id for p in action.responsible_parties.all()))
                    org_ids.add(action.primary_org_id)
                    opa_lists = (organization_plan_admins.get(org_id, []) for org_id in org_ids)
                    recipients += set(recipient for opas in opa_lists for recipient in opas)
                    if not recipients and fall_back_to_plan_admins:
                        recipients += plan_admins

        if self.concerns_indicator:
            if not indicator:
                raise Exception(f'Notifications of type {self.type} must refer to an indicator')
            recipients += indicator_contacts.get(indicator.id, [])
            if not recipients:
                if fall_back_to_org_admins:
                    recipients += organization_plan_admins.get(indicator.organization_id, [])
                    if not recipients and fall_back_to_plan_admins:
                        recipients += plan_admins

        return recipients

    def get_email_recipient(self) -> typing.Optional[EmailRecipient]:
        from .recipients import EmailRecipient
        if not self.custom_email:
            return None
        # FIXME: This sucks
        plan = self.base.plan
        client = plan.clients.first()
        if client:
            client = client.client
        else:
            admin = plan.general_admins.first()
            if admin:
                client = admin.get_admin_client()
        assert client
        return EmailRecipient(email=self.custom_email, client=client)


class ContentBlockManager(models.Manager):
    def get_by_natural_key(self, base, template, identifier):
        return self.get(
            base=base,
            template=template,
            identifier=identifier
        )


class ContentBlock(models.Model):
    content = RichTextField(verbose_name=_('content'), help_text=_('HTML content for the block'))

    base = ParentalKey(BaseTemplate, on_delete=models.PROTECT, related_name='content_blocks', editable=False)
    template = models.ForeignKey(
        NotificationTemplate, null=True, blank=True, on_delete=models.PROTECT, related_name='content_blocks',
        verbose_name=_('template'), help_text=_('Do not set if content block is used in multiple templates')
    )
    identifier = models.CharField(max_length=50, verbose_name=_('identifier'), choices=(
        ('intro', _('Introduction block')),
        ('motivation', _('Motivation block')),
        ('outro', _('Contact information block')),
    ))

    objects = ContentBlockManager()

    class Meta:
        ordering = ('base', 'identifier')
        verbose_name = _('content block')
        verbose_name_plural = _('content blocks')
        unique_together = (('base', 'template', 'identifier'),)

    def natural_key(self):
        return (self.base, self.template, self.identifier)
    natural_key.dependencies = [
        'notifications.BaseTemplate', 'notifications.NotificationTemplate'
    ]

    def save(self, *args, **kwargs):
        if self.template is not None:
            if self.template.base != self.base:
                raise Exception('Mismatch between template base and content block base')
        return super().save(*args, **kwargs)

    def __str__(self):
        parts = []
        if (self.template is not None):
            parts.append(self.template.get_type_display())
        parts.append(self.get_identifier_display())
        return ': '.join(parts)


class GeneralPlanAdminNotificationPreferences(models.Model):
    general_plan_admin = models.OneToOneField(
        'actions.GeneralPlanAdmin', related_name='notification_preferences', on_delete=models.CASCADE,
    )
    receive_feedback_notifications = models.BooleanField(
        verbose_name=_("receive feedback notifications"), default=True
    )


class ActionContactPersonNotificationPreferences(models.Model):
    action_contact_person = models.OneToOneField(
        'actions.ActionContactPerson', related_name='notification_preferences', on_delete=models.CASCADE,
    )
    receive_general_action_notifications = models.BooleanField(
        verbose_name=_("receive general action notifications"), default=True
    )
    receive_action_feedback_notifications = models.BooleanField(
        verbose_name=_("receive action feedback notifications"), default=True
    )
