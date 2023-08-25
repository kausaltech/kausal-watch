from __future__ import annotations
import typing

import reversion
from autoslug.fields import AutoSlugField
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from modelcluster.models import ClusterableModel, ParentalKey, ParentalManyToManyField
from modeltrans.fields import TranslationField
from wagtail.fields import RichTextField

from aplans.utils import (
    ChoiceArrayField, InstancesEditableByMixin, InstancesVisibleForMixin, OrderedModel, get_supported_languages
)
from indicators.models import Unit

if typing.TYPE_CHECKING:
    from .plan import Plan
    from users.models import User


class AttributeTypeQuerySet(models.QuerySet['AttributeType']):
    def for_categories(self, plan: 'Plan'):
        from .category import CategoryType

        ct = ContentType.objects.get_for_model(CategoryType)
        ct_qs = CategoryType.objects.filter(plan=plan).values('id')
        f = Q(scope_content_type=ct) & Q(scope_id__in=ct_qs)
        return self.filter(f)

    def for_actions(self, plan: 'Plan'):
        from .plan import Plan

        ct = ContentType.objects.get_for_model(Plan)
        f = Q(scope_content_type=ct) & Q(scope_id=plan.id)
        return self.filter(f)


@reversion.register(follow=['choice_options'])
class AttributeType(InstancesEditableByMixin, InstancesVisibleForMixin, ClusterableModel, OrderedModel):
    class AttributeFormat(models.TextChoices):
        ORDERED_CHOICE = 'ordered_choice', _('Ordered choice')
        OPTIONAL_CHOICE_WITH_TEXT = 'optional_choice', _('Optional choice with optional text')
        TEXT = 'text', _('Text')
        RICH_TEXT = 'rich_text', _('Rich text')
        NUMERIC = 'numeric', _('Numeric')
        CATEGORY_CHOICE = 'category_choice', _('Category')

    # Model to whose instances attributes of this type can be attached
    # TODO: Enforce Action or Category
    object_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')

    # An instance that this attribute type is specific to (e.g., a plan or a category type) so that it is only shown for
    # objects within the that scope.
    # TODO: Enforce Plan or CategoryType
    scope_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    scope_id = models.PositiveIntegerField()
    scope = GenericForeignKey('scope_content_type', 'scope_id')

    name = models.CharField(max_length=100, verbose_name=_('name'))
    identifier = AutoSlugField(
        always_update=True,
        populate_from='name',
        unique_with=('object_content_type', 'scope_content_type', 'scope_id'),
    )
    help_text = models.TextField(verbose_name=_('help text'), blank=True)
    format = models.CharField(max_length=50, choices=AttributeFormat.choices, verbose_name=_('Format'))
    unit = models.ForeignKey(
        Unit, blank=True, null=True, on_delete=models.PROTECT, related_name='+',
        verbose_name=_('Unit (only if format is numeric)'),
    )
    attribute_category_type = models.ForeignKey(
        'actions.CategoryType', blank=True, null=True, on_delete=models.CASCADE, related_name='+',
        verbose_name=_('Category type (if format is category)'),
        help_text=_('If the format is "Category", choose which category type the field values can be chosen from'),
    )
    show_choice_names = models.BooleanField(
        default=True, verbose_name=_('show choice names'),
        help_text=_('If the format is "ordered choice", determines whether the choice names are displayed'),
    )
    has_zero_option = models.BooleanField(
        default=False, verbose_name=_('has zero option'),
        help_text=_('If the format is "ordered choice", determines whether the first option is displayed with zero '
                    'bullets instead of one'),
    )
    max_length = models.PositiveIntegerField(blank=True, null=True, verbose_name=_('character limit for text fields'))
    show_in_reporting_tab = models.BooleanField(default=False, verbose_name=_('show in reporting tab'))
    choice_attributes: models.manager.RelatedManager[AttributeChoice]

    primary_language = models.CharField(max_length=8, choices=get_supported_languages())
    other_languages = ChoiceArrayField(
        models.CharField(max_length=8, choices=get_supported_languages()),
        default=list, null=True, blank=True
    )

    i18n = TranslationField(
        fields=('name', 'help_text'),
        # FIXME: This unfortunately duplicates the primary language of the plan of `scope` because we have no way of
        # easily accessing it with modeltrans. It should be kept in sync with the language of the plan of `scope`, but
        # it isn't at the moment because we hopefully will never change the primary language of a plan.
        default_language_field='primary_language',
    )

    public_fields = [
        'id', 'identifier', 'name', 'help_text', 'format', 'unit', 'attribute_category_type', 'show_choice_names',
        'has_zero_option', 'choice_options',
    ]

    objects: models.Manager[AttributeType] = models.Manager.from_queryset(AttributeTypeQuerySet)()

    class Meta:
        unique_together = (('object_content_type', 'scope_content_type', 'scope_id', 'identifier'),)
        verbose_name = _('field')
        verbose_name_plural = _('fields')
        ordering = ('scope_content_type', 'scope_id', 'order',)

    def clean(self):
        if self.unit is not None and self.format != self.AttributeFormat.NUMERIC:
            raise ValidationError({'unit': _('Unit must only be used for numeric attribute types')})
        if not self.primary_language and self.other_languages:
            raise ValidationError(_('If no primary language is set, there must not be other languages'))

    def save(self, *args, **kwargs):
        if not self.primary_language:
            assert not self.other_languages
            scope_app_label = self.scope_content_type.app_label
            scope_model = self.scope_content_type.model
            if scope_app_label == 'actions' and scope_model == 'plan':
                plan = self.scope
            elif scope_app_label == 'actions' and scope_model == 'categorytype':
                plan = self.scope.plan
            else:
                raise Exception(f"Unexpected AttributeType scope content type {scope_app_label}:{scope_model}")
            self.primary_language = plan.primary_language
            self.other_languages = plan.other_languages
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name_i18n


class Attribute:
    pass


class AttributeQuerySet(models.QuerySet):
    def visible_for_user(self, user: User, plan: typing.Optional[Plan]):
        if user.is_superuser:
            return self
        permissions = [InstancesVisibleForMixin.VisibleFor.PUBLIC]
        if user.is_authenticated:
            permissions.append(InstancesVisibleForMixin.VisibleFor.AUTHENTICATED)
            is_plan_admin = plan is not None and user.is_general_admin_for_plan(plan)
            if is_plan_admin:
                permissions.append(InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS)
            # FIXME: Check if the user is a contact person for the object, not for *anything* in the plan.
            is_contact_person = plan is not None and user.is_contact_person_in_plan(plan)
            if is_contact_person or is_plan_admin:
                permissions.append(InstancesVisibleForMixin.VisibleFor.CONTACT_PERSONS)
        return self.filter(type__instances_visible_for__in=permissions)


@reversion.register()
class AttributeTypeChoiceOption(ClusterableModel, OrderedModel):
    type = ParentalKey(AttributeType, on_delete=models.CASCADE, related_name='choice_options')
    name = models.CharField(max_length=100, verbose_name=_('name'))
    identifier = AutoSlugField(
        always_update=True,
        populate_from='name',
        unique_with='type',
    )

    i18n = TranslationField(
        fields=('name',),
        default_language_field='type__primary_language',
    )

    public_fields = ['id', 'identifier', 'name']

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['type', 'identifier'],
                name='unique_identifier_per_type',
            ),
            models.UniqueConstraint(
                fields=['type', 'order'],
                name='unique_order_per_type',
                deferrable=models.Deferrable.DEFERRED,
            ),
        ]
        ordering = ('type', 'order')
        verbose_name = _('attribute choice option')
        verbose_name_plural = _('attribute choice options')

    def __str__(self):
        return self.name


@reversion.register(follow=['categories'])
class AttributeCategoryChoice(Attribute, ClusterableModel):
    type = ParentalKey(AttributeType, on_delete=models.CASCADE, related_name='category_choice_attributes')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    categories = ParentalManyToManyField('actions.Category', related_name='+')

    objects = models.Manager.from_queryset(AttributeQuerySet)()

    public_fields = ['id', 'categories']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return "; ".join([str(c) for c in self.categories.all()])


@reversion.register(follow=['choice'])
class AttributeChoice(Attribute, models.Model):
    type = ParentalKey(AttributeType, on_delete=models.CASCADE, related_name='choice_attributes')

    # `content_object` must fit `type`
    # TODO: Enforce this
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    choice = models.ForeignKey(
        AttributeTypeChoiceOption, on_delete=models.CASCADE, related_name='choice_attributes'
    )

    objects = models.Manager.from_queryset(AttributeQuerySet)()

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return str(self.choice)


@reversion.register(follow=['choice'])
class AttributeChoiceWithText(Attribute, models.Model):
    type = ParentalKey(AttributeType, on_delete=models.CASCADE,
                       related_name='choice_with_text_attributes')

    # `content_object` must fit `type`
    # TODO: Enforce this
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    choice = models.ForeignKey(
        AttributeTypeChoiceOption, blank=True, null=True, on_delete=models.CASCADE,
        related_name='choice_with_text_attributes',
    )
    text = RichTextField(verbose_name=_('Text'), blank=True, null=True)

    i18n = TranslationField(
        fields=('text',),
        default_language_field='type__primary_language',
    )

    objects = models.Manager.from_queryset(AttributeQuerySet)()

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return f'{self.choice}; {self.text}'


@reversion.register()
class AttributeText(Attribute, models.Model):
    type = ParentalKey(
        AttributeType,
        on_delete=models.CASCADE,
        related_name='text_attributes',
    )

    # `content_object` must fit `type`
    # TODO: Enforce this
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    text = models.TextField(verbose_name=_('Text'))

    i18n = TranslationField(
        fields=('text',),
        default_language_field='type__primary_language',
    )

    objects = models.Manager.from_queryset(AttributeQuerySet)()

    public_fields = ['id', 'type', 'text']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return self.text_i18n


@reversion.register()
class AttributeRichText(Attribute, models.Model):
    type = ParentalKey(
        AttributeType,
        on_delete=models.CASCADE,
        related_name='rich_text_attributes',
    )

    # `content_object` must fit `type`
    # TODO: Enforce this
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    text = RichTextField(verbose_name=_('Text'))

    i18n = TranslationField(
        fields=('text',),
        default_language_field='type__primary_language',
    )

    objects = models.Manager.from_queryset(AttributeQuerySet)()

    public_fields = ['id', 'type', 'text']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return self.text_i18n


@reversion.register()
class AttributeNumericValue(Attribute, models.Model):
    type = ParentalKey(AttributeType, on_delete=models.CASCADE, related_name='numeric_value_attributes')

    # `content_object` must fit `type`
    # TODO: Enforce this
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    value = models.FloatField()

    objects = models.Manager.from_queryset(AttributeQuerySet)()

    public_fields = ['id', 'type', 'value']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return str(self.value)


class ModelWithAttributes(models.Model):
    """Fields for models with attributes.

    Models inheriting from this should implement the method
    get_attribute_type_by_identifier(self, identifier).
    """
    choice_attributes = GenericRelation(to='actions.AttributeChoice')
    choice_with_text_attributes = GenericRelation(to='actions.AttributeChoiceWithText')
    text_attributes = GenericRelation(to='actions.AttributeText')
    rich_text_attributes = GenericRelation(to='actions.AttributeRichText')
    numeric_value_attributes = GenericRelation(to='actions.AttributeNumericValue')
    category_choice_attributes = GenericRelation(to='actions.AttributeCategoryChoice')

    # Register models inheriting from this one using:
    # @reversion.register(follow=ModelWithAttributes.REVERSION_FOLLOW)
    REVERSION_FOLLOW = [
        'choice_attributes', 'choice_with_text_attributes', 'text_attributes', 'rich_text_attributes',
        'numeric_value_attributes', 'category_choice_attributes',
    ]

    def set_choice_attribute(self, type, choice_option_id):
        if isinstance(type, str):
            type = self.get_attribute_type_by_identifier(type)
        try:
            existing_attribute = self.choice_attributes.get(type=type)
        except self.choice_attributes.model.DoesNotExist:
            if choice_option_id is not None:
                self.choice_attributes.create(type=type, choice_id=choice_option_id)
        else:
            if choice_option_id is None:
                existing_attribute.delete()
            else:
                existing_attribute.choice_id = choice_option_id
                existing_attribute.save()

    def set_choice_with_text_attribute(self, type, choice_option_id, text):
        if isinstance(type, str):
            type = self.get_attribute_type_by_identifier(type)
        try:
            existing_attribute = self.choice_with_text_attributes.get(type=type)
        except self.choice_with_text_attributes.model.DoesNotExist:
            if choice_option_id is not None or text:
                self.choice_with_text_attributes.create(
                    type=type,
                    choice_id=choice_option_id,
                    text=text,
                )
        else:
            if choice_option_id is None and not text:
                existing_attribute.delete()
            else:
                existing_attribute.choice_id = choice_option_id
                existing_attribute.text = text
                existing_attribute.save()

    def set_numeric_value_attribute(self, type, value):
        if isinstance(type, str):
            type = self.get_attribute_type_by_identifier(type)
        try:
            existing_attribute = self.numeric_value_attributes.get(type=type)
        except self.numeric_value_attributes.model.DoesNotExist:
            if value is not None:
                self.numeric_value_attributes.create(type=type, value=value)
        else:
            if value is None:
                existing_attribute.delete()
            else:
                existing_attribute.value = value
                existing_attribute.save()

    def set_text_attribute(self, type, value):
        if isinstance(type, str):
            type = self.get_attribute_type_by_identifier(type)
        try:
            existing_attribute = self.text_attributes.get(type=type)
        except self.text_attributes.model.DoesNotExist:
            if value is not None:
                self.text_attributes.create(type=type, text=value)
        else:
            if value is None:
                existing_attribute.delete()
            else:
                existing_attribute.text = value
                existing_attribute.save()

    def set_rich_text_attribute(self, type, value):
        if isinstance(type, str):
            type = self.get_attribute_type_by_identifier(type)
        try:
            existing_attribute = self.rich_text_attributes.get(type=type)
        except self.rich_text_attributes.model.DoesNotExist:
            if value is not None:
                self.rich_text_attributes.create(type=type, text=value)
        else:
            if value is None:
                existing_attribute.delete()
            else:
                existing_attribute.text = value
                existing_attribute.save()

    def set_category_choice_attribute(self, type, category_ids):
        if isinstance(type, str):
            type = self.get_attribute_type_by_identifier(type)
        try:
            existing_attribute = self.category_choice_attributes.get(type=type)
        except self.category_choice_attributes.model.DoesNotExist:
            if category_ids:
                attribute = self.category_choice_attributes.create(type=type)
                attribute.categories.set(category_ids)
        else:
            if not category_ids:
                existing_attribute.delete()
            else:
                existing_attribute.categories.set(category_ids)

    class Meta:
        abstract = True
