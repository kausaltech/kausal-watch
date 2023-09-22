from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString
from wagtail import blocks

from actions.blocks.choosers import CategoryAttributeTypeChooserBlock
from actions.models.attributes import AttributeType


@register_streamfield_block
class CategoryPageAttributeTypeBlock(blocks.StructBlock):
    attribute_type = CategoryAttributeTypeChooserBlock(required=True)

    model_instance_container_blocks = {
        AttributeType: 'attribute_type',
    }

    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeType, required=True)
    ]


@register_streamfield_block
class CategoryPageBodyBlock(blocks.StructBlock):
    pass


@register_streamfield_block
class CategoryPageCategoryListBlock(blocks.StructBlock):
    pass


@register_streamfield_block
class CategoryPageContactFormBlock(blocks.StructBlock):
    heading = blocks.CharBlock(required=False)
    description = blocks.CharBlock(required=False)

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLString('description'),
    ]


@register_streamfield_block
class CategoryPageProgressBlock(blocks.StructBlock):
    basis = blocks.ChoiceBlock(choices=[
        ('implementation_phase', _('Implementation phase')),
        ('status', _('Status')),
    ])


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
