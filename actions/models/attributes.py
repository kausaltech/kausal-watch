from __future__ import annotations
import typing

import reversion
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from modelcluster.models import ClusterableModel, ParentalKey
from wagtail.core.fields import RichTextField

from aplans.utils import IdentifierField, InstancesEditableByMixin, OrderedModel
from indicators.models import Unit

if typing.TYPE_CHECKING:
    from .plan import Plan


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


@reversion.register()
class AttributeType(InstancesEditableByMixin, ClusterableModel, OrderedModel):
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

    identifier = IdentifierField()
    name = models.CharField(max_length=100, verbose_name=_('name'))
    help_text = models.TextField(verbose_name=_('help text'), blank=True)
    format = models.CharField(max_length=50, choices=AttributeFormat.choices, verbose_name=_('Format'))
    unit = models.ForeignKey(
        Unit, blank=True, null=True, on_delete=models.PROTECT, related_name='+',
        verbose_name=_('Unit (only if format is numeric)'),
    )
    attribute_category_type = models.ForeignKey(
        'actions.CategoryType', blank=True, null=True, on_delete=models.CASCADE, related_name='+',
        verbose_name=_('Category type (if format is category)'),
        help_text=_('If the format is "Category", choose which category type the attribute values can be chosen from'),
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
    report = models.ForeignKey(
        'actions.Report', blank=True, null=True, on_delete=models.PROTECT,
        related_name='attribute_types', verbose_name=_('Report'),
    )
    choice_attributes: models.manager.RelatedManager[AttributeChoice]

    public_fields = [
        'id', 'identifier', 'name', 'help_text', 'format', 'unit', 'show_choice_names', 'has_zero_option',
        'choice_options',
    ]

    objects: models.Manager[AttributeType] = models.Manager.from_queryset(AttributeTypeQuerySet)()

    class Meta:
        unique_together = (('object_content_type', 'scope_content_type', 'scope_id', 'identifier'),)
        verbose_name = _('attribute type')
        verbose_name_plural = _('attribute types')

    def clean(self):
        if self.unit is not None and self.format != self.AttributeFormat.NUMERIC:
            raise ValidationError({'unit': _('Unit must only be used for numeric attribute types')})

    def set_value(self, obj, vals):
        # TODO: Remove equivalent from category.py
        content_type = ContentType.objects.get_for_model(obj)
        assert content_type.app_label == 'actions'
        if content_type.model == 'action':
            assert self.scope == obj.plan
        elif content_type.model == 'category':
            assert self.scope == obj.type
        else:
            raise ValueError(f"Invalid content type {content_type.app_label}.{content_type.model}")

        if self.format == self.AttributeFormat.ORDERED_CHOICE:
            val = vals.get('choice')
            existing = self.choice_attributes.filter(content_type=content_type, object_id=obj.id)
            if existing:
                existing.delete()
            if val is not None:
                AttributeChoice.objects.create(type=self, content_object=obj, choice=val)
        elif self.format == self.AttributeFormat.CATEGORY_CHOICE:
            category_val = vals.get('categories')
            existing = self.category_choice_attributes.filter(content_type=content_type, object_id=obj.id)
            if existing:
                existing.delete()
            if category_val is not None:
                acc = AttributeCategoryChoice.objects.create(type=self, content_object=obj)
                acc.categories.set(category_val)
        elif self.format == self.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT:
            choice_val = vals.get('choice')
            text_val = vals.get('text')
            existing = self.choice_with_text_attributes.filter(content_type=content_type, object_id=obj.id)
            if existing:
                existing.delete()
            if choice_val is not None or text_val:
                AttributeChoiceWithText.objects.create(
                    type=self,
                    content_object=obj,
                    choice=choice_val,
                    text=text_val,
                )
        elif self.format == self.AttributeFormat.TEXT:
            val = vals.get('text')
            try:
                obj = self.text_attributes.get(content_type=content_type, object_id=obj.id)
            except self.text_attributes.model.DoesNotExist:
                if val:
                    obj = AttributeText.objects.create(type=self, content_object=obj, text=val)
            else:
                if not val:
                    obj.delete()
                else:
                    obj.text = val
                    obj.save()
        elif self.format == self.AttributeFormat.RICH_TEXT:
            val = vals.get('text')
            try:
                obj = self.rich_text_attributes.get(content_type=content_type, object_id=obj.id)
            except self.rich_text_attributes.model.DoesNotExist:
                if val:
                    obj = AttributeRichText.objects.create(type=self, content_object=obj, text=val)
            else:
                if not val:
                    obj.delete()
                else:
                    obj.text = val
                    obj.save()
        elif self.format == self.AttributeFormat.NUMERIC:
            val = vals.get('value')
            try:
                obj = self.numeric_value_attributes.get(content_type=content_type, object_id=obj.id)
            except self.numeric_value_attributes.model.DoesNotExist:
                if val is not None:
                    obj = AttributeNumericValue.objects.create(type=self, content_object=obj, value=val)
            else:
                if val is None:
                    obj.delete()
                else:
                    obj.value = val
                    obj.save()
        else:
            raise Exception(f"Unsupported attribute type format: {self.format}")

    def __str__(self):
        return self.name


class AttributeTypeChoiceOption(ClusterableModel, OrderedModel):
    type = ParentalKey(AttributeType, on_delete=models.CASCADE, related_name='choice_options')
    identifier = IdentifierField()
    name = models.CharField(max_length=100, verbose_name=_('name'))

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


class AttributeCategoryChoice(models.Model):
    type = ParentalKey(AttributeType, on_delete=models.CASCADE, related_name='category_choice_attributes')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    categories = models.ManyToManyField(
        'actions.Category', related_name='+'
    )

    public_fields = ['id', 'categories']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        categories = ", ".join([str(c) for c in self.categories.all()])
        return f'[{categories}] ({self.type}) for {self.content_object} ({self.content_type})'


class AttributeChoice(models.Model):
    type = ParentalKey(AttributeType, on_delete=models.CASCADE, related_name='choice_attributes')

    # `content_object` must fit `type`
    # TODO: Enforce this
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    choice = models.ForeignKey(
        AttributeTypeChoiceOption, on_delete=models.CASCADE, related_name='choice_attributes'
    )

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return '%s (%s) for %s' % (self.choice, self.type, self.content_object)


class AttributeChoiceWithText(models.Model):
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

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return '%s; %s (%s) for %s' % (self.choice, self.text, self.type, self.content_object)


class AttributeText(models.Model):
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

    public_fields = ['id', 'type', 'text']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return '%s for %s' % (self.type, self.content_object)


class AttributeRichText(models.Model):
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

    public_fields = ['id', 'type', 'text']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return '%s for %s' % (self.type, self.content_object)


class AttributeNumericValue(models.Model):
    type = ParentalKey(AttributeType, on_delete=models.CASCADE, related_name='numeric_value_attributes')

    # `content_object` must fit `type`
    # TODO: Enforce this
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()

    value = models.FloatField()

    public_fields = ['id', 'type', 'value']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return '%s (%s) for %s' % (self.value, self.type, self.content_object)


class ModelWithAttributes(models.Model):
    """Fields for models with attributes.

    Models inheriting from this should implement the method
    get_attribute_type_by_identifier(self, identifier).
    """
    choice_attributes = GenericRelation(to='actions.AttributeChoice')
    choice_with_text_attributes = GenericRelation(to='actions.AttributeChoiceWithText')
    rich_text_attributes = GenericRelation(to='actions.AttributeRichText')
    numeric_value_attributes = GenericRelation(to='actions.AttributeNumericValue')
    category_choice_attributes = GenericRelation(to='actions.AttributeCategoryChoice')

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

    class Meta:
        abstract = True
