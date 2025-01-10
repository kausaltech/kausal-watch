from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString

from actions.blocks.choosers import (
    CategoryAttributeTypeChooserBlock,
    CategoryChooserBlock,
    CategoryLevelChooserBlock,
    CategoryTypeChooserBlock,
)
from actions.models.attributes import AttributeType
from actions.models.category import Category, CategoryLevel, CategoryType


@register_streamfield_block
class CategoryListBlock(blocks.StructBlock):
    category_type = CategoryTypeChooserBlock(required=False)
    category = CategoryChooserBlock(required=False)
    heading = blocks.CharBlock(classname='full title', label=_('Heading'), required=False)
    lead = blocks.RichTextBlock(label=_('Lead'), required=False)
    style = blocks.ChoiceBlock(label=_('Style'), choices=[
        ('cards', _('Cards')),
        ('table', _('Table')),
    ])

    class Meta:
        label = _('Category list')

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType),
        GraphQLForeignKey('category', Category),
        GraphQLString('heading'),
        GraphQLString('lead'),
        GraphQLString('style'),
    ]


@register_streamfield_block
class CategoryTreeMapBlock(blocks.StructBlock):
    heading = blocks.CharBlock(classname='full title', label=_('Heading'), required=False)
    lead = blocks.RichTextBlock(label=_('Lead'), required=False)

    category_type = CategoryTypeChooserBlock(required=True)
    value_attribute = CategoryAttributeTypeChooserBlock(label=_('Value field'), required=True)

    class Meta:
        label = _('Category tree map')

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType),
        GraphQLForeignKey('value_attribute', AttributeType),
        GraphQLString('heading'),
        GraphQLString('lead'),
    ]



@register_streamfield_block
class CategoryTypeLevelListBlock(blocks.StructBlock):
    heading = blocks.CharBlock(
        required=False,
        help_text=_("What heading should be used in the public UI for the Category level list?"),
        default='',
        label=_("Heading"),
    )
    help_text = blocks.CharBlock(
        required=False,
        help_text=_("Help text for the Category level list to be shown in the public UI"),
        default='',
        label = _("Help text"),
    )

    category_type = CategoryTypeChooserBlock(required=True)
    category_level = CategoryLevelChooserBlock(required=True, label = _("Filter by level"))
    group_by_category_level = CategoryLevelChooserBlock(
        required=False, label= _("Group by level"),
        help_text=_("Use category level for tabbed grouping in the public UI"))

    class Meta:
        label = _("Category level list")

    graphql_fields = [
        GraphQLString('heading', required=False),
        GraphQLString('help_text', required=False),
        GraphQLForeignKey('category_type', CategoryType, required=True),
        GraphQLForeignKey('category_level', CategoryLevel, required=True),
        GraphQLForeignKey('group_by_category_level', CategoryLevel, required=False),
    ]
