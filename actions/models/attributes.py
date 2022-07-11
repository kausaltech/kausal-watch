import reversion
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.models import ClusterableModel, ParentalKey
from wagtail.core.fields import RichTextField

from aplans.utils import IdentifierField, OrderedModel
from indicators.models import Unit


@reversion.register()
class AttributeType(ClusterableModel, OrderedModel):
    class AttributeFormat(models.TextChoices):
        ORDERED_CHOICE = 'ordered_choice', _('Ordered choice')
        OPTIONAL_CHOICE_WITH_TEXT = 'optional_choice', _('Optional choice with optional text')
        RICH_TEXT = 'rich_text', _('Rich text')
        NUMERIC = 'numeric', _('Numeric')

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
    format = models.CharField(max_length=50, choices=AttributeFormat.choices, verbose_name=_('Format'))
    unit = models.ForeignKey(
        Unit, blank=True, null=True, on_delete=models.PROTECT, related_name='+',
        verbose_name=_('Unit (only if format is numeric)'),
    )

    public_fields = [
        'identifier', 'name', 'format', 'unit', 'choice_options'
    ]

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
        unique_together = (('type', 'identifier'), ('type', 'order'),)
        ordering = ('type', 'order')
        verbose_name = _('attribute choice option')
        verbose_name_plural = _('attribute choice options')

    def __str__(self):
        return self.name


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
