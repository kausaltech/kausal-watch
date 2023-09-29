from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString
from wagtail import blocks

from actions.blocks.choosers import CategoryAttributeTypeChooserBlock
from actions.models.attributes import AttributeType


@register_streamfield_block
class CategoryPageAttributeTypeBlock(blocks.StructBlock):
    attribute_type = CategoryAttributeTypeChooserBlock(required=True)

    class Meta:
        label = _('Field')

    model_instance_container_blocks = {
        AttributeType: 'attribute_type',
    }

    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeType, required=True)
    ]


@register_streamfield_block
class CategoryPageBodyBlock(blocks.StructBlock):
    class Meta:
        label = _('Body')


@register_streamfield_block
class CategoryPageCategoryListBlock(blocks.StructBlock):
    class Meta:
        label = _('Category list')


@register_streamfield_block
class CategoryPageContactFormBlock(blocks.StructBlock):
    heading = blocks.CharBlock(required=False, label=_('Heading'))
    description = blocks.CharBlock(required=False, label=_('Description'))

    class Meta:
        label = _('Contact form')

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLString('description'),
    ]


@register_streamfield_block
class CategoryPageProgressBlock(blocks.StructBlock):
    basis = blocks.ChoiceBlock(label=_('Basis'), choices=[
        ('implementation_phase', _('Implementation phase')),
        ('status', _('Status')),
    ])

    class Meta:
        label = _('Progress')


@register_streamfield_block
class CategoryPageMainTopBlock(blocks.StreamBlock):
    attribute = CategoryPageAttributeTypeBlock()
    progress = CategoryPageProgressBlock()

    graphql_types = [
        CategoryPageAttributeTypeBlock,
        CategoryPageProgressBlock,
    ]


@register_streamfield_block
class CategoryPageMainBottomBlock(blocks.StreamBlock):
    attribute = CategoryPageAttributeTypeBlock()
    body = CategoryPageBodyBlock()
    category_list = CategoryPageCategoryListBlock()
    contact_form = CategoryPageContactFormBlock()
    # TODO: CategoryPageSectionBlock

    graphql_types = [
        CategoryPageAttributeTypeBlock,
        CategoryPageBodyBlock,
        CategoryPageCategoryListBlock,
        CategoryPageContactFormBlock,
    ]


@register_streamfield_block
class CategoryPageAsideBlock(blocks.StreamBlock):
    attribute = CategoryPageAttributeTypeBlock()
    # TODO: CategoryPageSectionBlock

    graphql_types = [
        CategoryPageAttributeTypeBlock,
    ]
