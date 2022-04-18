from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField

import reversion

from aplans.utils import (
    IdentifierField, OrderedModel, PlanRelatedModel, generate_identifier,
    validate_css_color
)


@reversion.register()
class CategoryType(ClusterableModel, PlanRelatedModel):
    """Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """
    class SelectWidget(models.TextChoices):
        MULTIPLE = 'multiple', _('Multiple')
        SINGLE = 'single', _('Single')

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
    select_widget = models.CharField(max_length=30, choices=SelectWidget.choices)
    i18n = TranslationField(fields=('name',))

    categories: models.QuerySet[Category]

    public_fields = [
        'id', 'plan', 'name', 'identifier', 'editable_for_actions', 'editable_for_indicators',
        'usable_for_indicators', 'usable_for_actions', 'levels', 'categories', 'attribute_types',
        'hide_category_identifiers', 'select_widget',
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
        'color', 'children', 'category_pages', 'indicators',
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
