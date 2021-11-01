from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from wagtail.core.fields import RichTextField

import reversion

from aplans.utils import (
    IdentifierField, OrderedModel, PlanRelatedModel, generate_identifier,
    validate_css_color
)


class CategoryType(ClusterableModel, PlanRelatedModel):
    """Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    plan = models.ForeignKey('actions.Plan', on_delete=models.CASCADE, related_name='category_types')
    name = models.CharField(max_length=50, verbose_name=_('name'))
    identifier = IdentifierField()
    usable_for_actions = models.BooleanField(
        default=False,
        verbose_name=_('usable for action categorization'),
    )
    usable_for_indicators = models.BooleanField(
        default=False,
        verbose_name=_('usable for indicator categorization'),
    )
    editable_for_actions = models.BooleanField(
        default=False,
        verbose_name=_('editable for actions'),
    )
    editable_for_indicators = models.BooleanField(
        default=False,
        verbose_name=_('editable for indicators'),
    )
    hide_category_identifiers = models.BooleanField(
        default=False, verbose_name=_('hide category identifiers'),
        help_text=_("Set if the categories do not have meaningful identifiers")
    )

    public_fields = [
        'id', 'plan', 'name', 'identifier', 'editable_for_actions', 'editable_for_indicators',
        'usable_for_indicators', 'usable_for_actions', 'levels', 'categories', 'metadata',
        'hide_category_identifiers',
    ]

    class Meta:
        unique_together = (('plan', 'identifier'),)
        ordering = ('plan', 'name')
        verbose_name = _('category type')
        verbose_name_plural = _('category types')

    def __str__(self):
        return "%s (%s:%s)" % (self.name, self.plan.identifier, self.identifier)


@reversion.register()
class CategoryLevel(OrderedModel):
    """Hierarchy level within a CategoryType.

    Root level has order=0, first child level order=1 and so on.
    """
    type = ParentalKey(
        CategoryType, on_delete=models.CASCADE, related_name='levels',
        verbose_name=_('type')
    )
    name = models.CharField(max_length=100, verbose_name=_('name'))
    name_plural = models.CharField(max_length=100, verbose_name=_('plural name'), null=True, blank=True)
    i18n = TranslationField(fields=('name',))

    public_fields = [
        'id', 'name', 'name_plural', 'order', 'type',
    ]

    class Meta:
        unique_together = (('type', 'order'),)
        verbose_name = _('category level')
        verbose_name_plural = _('category levels')
        ordering = ('type', 'order')

    def __str__(self):
        return self.name


@reversion.register()
class CategoryTypeMetadata(ClusterableModel, OrderedModel):
    class MetadataFormat(models.TextChoices):
        ORDERED_CHOICE = 'ordered_choice', _('Ordered choice')
        RICH_TEXT = 'rich_text', _('Rich text')
        NUMERIC = 'numeric', _('Numeric')

    type = ParentalKey(CategoryType, on_delete=models.CASCADE, related_name='metadata')
    identifier = IdentifierField()
    name = models.CharField(max_length=100, verbose_name=_('name'))
    format = models.CharField(max_length=50, choices=MetadataFormat.choices, verbose_name=_('Format'))

    public_fields = [
        'identifier', 'name', 'format', 'choices'
    ]

    class Meta:
        unique_together = (('type', 'identifier'),)
        verbose_name = _('category metadata')
        verbose_name_plural = _('category metadatas')

    def __str__(self):
        return self.name

    def filter_siblings(self, qs):
        return qs.filter(type=self.type)

    def set_category_value(self, category, val):
        assert category.type == self.type

        if self.format == self.MetadataFormat.ORDERED_CHOICE:
            existing = self.category_choices.filter(category=category)
            if existing:
                existing.delete()
            if val is not None:
                self.category_choices.create(category=category, choice=val)
        elif self.format == self.MetadataFormat.RICH_TEXT:
            try:
                obj = self.category_richtexts.get(category=category)
            except self.category_richtexts.model.DoesNotExist:
                if val:
                    obj = self.category_richtexts.create(category=category, text=val)
            else:
                if not val:
                    obj.delete()
                else:
                    obj.text = val
                    obj.save()
        elif self.format == self.MetadataFormat.NUMERIC:
            try:
                obj = self.category_numeric_values.get(category=category)
            except self.category_numeric_values.model.DoesNotExist:
                if val is not None:
                    obj = self.category_numeric_values.create(category=category, value=val)
            else:
                if val is None:
                    obj.delete()
                else:
                    obj.value = val
                    obj.save()


class CategoryTypeMetadataChoice(OrderedModel):
    metadata = ParentalKey(CategoryTypeMetadata, on_delete=models.CASCADE, related_name='choices')
    identifier = IdentifierField()
    name = models.CharField(max_length=100, verbose_name=_('name'))

    public_fields = [
        'identifier', 'name'
    ]

    class Meta:
        unique_together = (('metadata', 'identifier'), ('metadata', 'order'),)
        ordering = ('metadata', 'order')
        verbose_name = _('category type metadata choice')
        verbose_name_plural = _('category type metadata choices')

    def __str__(self):
        return self.name


class Category(ClusterableModel, OrderedModel, PlanRelatedModel):
    """A category for actions and indicators."""

    type = models.ForeignKey(
        CategoryType, on_delete=models.PROTECT, related_name='categories',
        verbose_name=_('type')
    )
    identifier = IdentifierField()
    external_identifier = models.CharField(max_length=50, blank=True, null=True, editable=False)
    name = models.CharField(max_length=100, verbose_name=_('name'))
    image = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children',
        verbose_name=_('parent category')
    )
    short_description = models.TextField(
        max_length=200, blank=True, verbose_name=_('short description')
    )
    color = models.CharField(
        max_length=50, blank=True, null=True, verbose_name=_('theme color'),
        help_text=_('Set if the category has a theme color'),
        validators=[validate_css_color]
    )

    i18n = TranslationField(fields=('name', 'short_description'))

    public_fields = [
        'id', 'type', 'order', 'identifier', 'external_identifier', 'name', 'parent', 'short_description',
        'color', 'children', 'category_page', 'indicators',
    ]

    class Meta:
        unique_together = (('type', 'identifier'), ('type', 'external_identifier'))
        verbose_name = _('category')
        verbose_name_plural = _('categories')
        ordering = ('type', 'order')

    def clean(self):
        if self.parent_id is not None:
            seen_categories = {self.id}
            obj = self.parent
            while obj is not None:
                if obj.id in seen_categories:
                    raise ValidationError({'parent': _('Parent forms a loop. Leave empty if top-level category.')})
                seen_categories.add(obj.id)
                obj = obj.parent

            if self.parent.type != self.type:
                raise ValidationError({'parent': _('Parent must be of same type')})

    def get_plans(self):
        return [self.type.plan]

    @classmethod
    def filter_by_plan(cls, plan, qs):
        return qs.filter(type__plan=plan)

    def set_plan(self, plan):
        # The right plan should be set through CategoryType relation, so
        # we do nothing here.
        pass

    def generate_identifier(self):
        self.identifier = generate_identifier(self.type.categories.all(), 'c', 'identifier')

    def __str__(self):
        if self.identifier and self.type and not self.type.hide_category_identifiers:
            return "%s %s" % (self.identifier, self.name)
        else:
            return self.name


class CategoryIcon(models.Model):
    category = models.OneToOneField(Category, on_delete=models.CASCADE, related_name='icon')
    data = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'Icon for %s' % self.category


class CategoryMetadataRichText(models.Model):
    metadata = models.ForeignKey(CategoryTypeMetadata, on_delete=models.CASCADE, related_name=_('category_richtexts'))
    category = ParentalKey(Category, on_delete=models.CASCADE, related_name=_('metadata_richtexts'))
    text = RichTextField(verbose_name=_('Text'))

    public_fields = [
        'id', 'metadata', 'category', 'text',
    ]

    class Meta:
        unique_together = ('category', 'metadata')

    def __str__(self):
        return '%s for %s' % (self.metadata, self.category)


class CategoryMetadataChoice(models.Model):
    metadata = models.ForeignKey(CategoryTypeMetadata, on_delete=models.CASCADE, related_name='category_choices')
    category = ParentalKey(Category, on_delete=models.CASCADE, related_name=_('metadata_choices'))
    choice = models.ForeignKey(CategoryTypeMetadataChoice, on_delete=models.CASCADE, related_name=_('categories'))

    class Meta:
        unique_together = ('category', 'metadata')

    def __str__(self):
        return '%s (%s) for %s' % (self.choice, self.metadata, self.category)


class CategoryMetadataNumericValue(models.Model):
    metadata = models.ForeignKey(CategoryTypeMetadata, on_delete=models.CASCADE, related_name='category_numeric_values')
    category = ParentalKey(Category, on_delete=models.CASCADE, related_name=_('metadata_numeric_values'))
    value = models.FloatField()

    public_fields = [
        'id', 'metadata', 'category', 'value',
    ]

    class Meta:
        unique_together = ('category', 'metadata')

    def __str__(self):
        return '%s (%s) for %s' % (self.value, self.metadata, self.category)
