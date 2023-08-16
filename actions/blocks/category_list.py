from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString
from wagtail import blocks

from actions.blocks.choosers import CategoryAttributeTypeChooserBlock, CategoryChooserBlock, CategoryTypeChooserBlock
from actions.models.attributes import AttributeType
from actions.models.category import Category, CategoryType


@register_streamfield_block
class CategoryListBlock(blocks.StructBlock):
    category_type = CategoryTypeChooserBlock(label=_('Category type'), required=False)
    category = CategoryChooserBlock(label=_('Category'), required=False)
    heading = blocks.CharBlock(classname='full title', label=_('Heading'), required=False)
    lead = blocks.RichTextBlock(label=_('Lead'), required=False)
    style = blocks.ChoiceBlock(choices=[
        ('cards', _('Cards')),
        ('table', _('Table')),
    ])

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

    category_type = CategoryTypeChooserBlock(label=_('Category type'), required=True)
    value_attribute = CategoryAttributeTypeChooserBlock(label=_('Value attribute'), required=True)

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType),
        GraphQLForeignKey('value_attribute', AttributeType),
        GraphQLString('heading'),
        GraphQLString('lead'),
    ]
