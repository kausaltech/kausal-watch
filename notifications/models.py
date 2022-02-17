import logging
from enum import Enum

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from modeltrans.fields import TranslationField

from actions.models import Plan
from people.models import Person

DEFAULT_LANG = settings.LANGUAGES[0][0]
logger = logging.getLogger('aplans.notifications')


class NotificationType(Enum):
    TASK_LATE = _("Task is late")
    TASK_DUE_SOON = _("Task is due soon")
    ACTION_NOT_UPDATED = _("Action metadata has not been updated recently")
    NOT_ENOUGH_TASKS = _("Action doesn't have enough in-progress tasks")
    UPDATED_INDICATOR_VALUES_LATE = _("Updated indicator values are late")
    UPDATED_INDICATOR_VALUES_DUE_SOON = _("Updated indicator values are due soon")

    @property
    def identifier(self):
        return self.name.lower()

    @property
    def verbose_name(self):
        return self.value


def notification_type_choice_builder():
    for val in NotificationType:
        yield (val.identifier, val.verbose_name)


class SentNotification(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    sent_at = models.DateTimeField()
    type = models.CharField(
        verbose_name=_('type'), choices=notification_type_choice_builder(),
        max_length=100
    )
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name='notifications')

    def __str__(self):
        return '%s: %s -> %s' % (self.content_object, self.type, self.person)


class BaseTemplateManager(models.Manager):
    def get_by_natural_key(self, plan_identifier):
        return self.get(plan__identifier=plan_identifier)


class BaseTemplate(models.Model):
    plan = models.OneToOneField(
        Plan, on_delete=models.CASCADE, related_name='notification_base_template',
        verbose_name=_('plan'),
    )
    from_name = models.CharField(verbose_name=_('Email From name'), null=True, blank=True, max_length=200)
    from_address = models.EmailField(verbose_name=_('Email From address'), null=True, blank=True)
    reply_to = models.CharField(verbose_name=_('Email Reply-To address'), null=True, blank=True, max_length=200)

    brand_dark_color = models.CharField(verbose_name=_('Brand dark color'), null=True, blank=True, max_length=30)
    logo = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    font_family = models.CharField(verbose_name=_('Font family'), null=True, blank=True, max_length=200)
    font_css_url = models.URLField(verbose_name=_('Font CSS style URL'), null=True, blank=True)

    i18n = TranslationField(fields=['from_name'])

    objects = BaseTemplateManager()

    class Meta:
        verbose_name = _('base template')
        verbose_name_plural = _('base templates')

    def __str__(self):
        return str(self.plan)

    def natural_key(self):
        return (self.plan.identifier,)

    def get_notification_context(self):
        return dict(theme=dict(
            brand_dark_color=self.brand_dark_color,
            font_family=self.font_family,
            font_css_url=self.font_css_url,
            link_in_brand_bg_color="#ffffff"
        ))


class NotificationTemplateManager(models.Manager):
    def get_by_natural_key(self, base, type_):
        return self.get(base__plan__identifier=base[0], type=type_)


class NotificationTemplate(models.Model):
    base = models.ForeignKey(BaseTemplate, on_delete=models.CASCADE, related_name='templates', editable=False)
    subject = models.CharField(
        verbose_name=_('subject'), max_length=200, help_text=_('Subject for email notifications')
    )
    type = models.CharField(
        verbose_name=_('type'), choices=notification_type_choice_builder(),
        max_length=100,
    )

    i18n = TranslationField(fields=['subject'])

    objects = NotificationTemplateManager()

    class Meta:
        verbose_name = _('notification template')
        verbose_name_plural = _('notification templates')
        unique_together = (('base', 'type'),)

    def __str__(self):
        for val in NotificationType:
            if val.identifier == self.type:
                return str(val.verbose_name)
        return 'N/A'

    def natural_key(self):
        return (self.base.natural_key(), self.type)
    natural_key.dependencies = ['notifications.BaseTemplate']

    def clean(self):
        pass


class ContentBlockManager(models.Manager):
    def get_by_natural_key(self, base, template, identifier):
        return self.get(
            base=base,
            template=template,
            identifier=identifier
        )


class ContentBlock(models.Model):
    content = models.TextField(verbose_name=_('content'), help_text=_('HTML content for the block'))

    base = models.ForeignKey(BaseTemplate, on_delete=models.CASCADE, related_name='content_blocks', editable=False)
    template = models.ForeignKey(
        NotificationTemplate, null=True, blank=True, on_delete=models.CASCADE, related_name='content_blocks',
        verbose_name=_('template'), help_text=_('Do not set if content block is used in multiple templates')
    )
    identifier = models.CharField(max_length=50, verbose_name=_('identifier'), choices=(
        ('intro', _('Introduction block')),
        ('motivation', _('Motivation block')),
        ('outro', _('Contact information block')),
    ))

    i18n = TranslationField(fields=['content'])

    objects = ContentBlockManager()

    class Meta:
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
