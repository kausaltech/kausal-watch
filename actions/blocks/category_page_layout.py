from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString

from actions.blocks.action_content import BaseContactFormBlock, BaseDatasetsBlock
from actions.blocks.choosers import (
    CategoryAttributeTypeChooserBlock,
    CategoryLevelChooserBlock,
    CategoryTypeDatasetSchemaChooserBlock,
)
from actions.models.attributes import AttributeType
from actions.models.category import CategoryLevel
from budget.models import DatasetSchema


@register_streamfield_block
class CategoryPageAttributeTypeBlock(blocks.StructBlock):
    attribute_type = CategoryAttributeTypeChooserBlock(required=True)

    class Meta:
        label = _('Field')

    model_instance_container_blocks = {
        AttributeType: 'attribute_type',
    }

    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeType, required=True),
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
class CategoryPageContactFormBlock(BaseContactFormBlock):
    class Meta:
        label = _("Contact form")


@register_streamfield_block
class CategoryTypeDatasetsBlock(BaseDatasetsBlock):
    dataset_schema = CategoryTypeDatasetSchemaChooserBlock(required=True)

    graphql_fields = BaseDatasetsBlock.graphql_fields + [
        GraphQLForeignKey('dataset_schema', DatasetSchema, required=True),
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
class CategoryTypeLevelListBlock(blocks.StructBlock):
    heading = blocks.CharBlock(
        required=False,
        help_text=_("What heading should be used in the public UI for the Category list?"),
        default='',
        label=_("Heading"),
    )
    help_text = blocks.CharBlock(
        required=False,
        help_text=_("Help text for the Category list to be shown in the public UI"),
        default='',
        label = _("Help text"),
    )

    category_level = CategoryLevelChooserBlock(required=True, label = _("Filter by level"), linked_fields={
                # ID of the hidden <input> element with the category type ID
                'type': '#panel-child-content-child-category_type-raw-value-id',
            })
    group_by_category_level = CategoryLevelChooserBlock(required=False, label = _("Group by level"), linked_fields={
                # ID of the hidden <input> element with the category type ID
                'type': '#panel-child-content-child-category_type-raw-value-id',
            })

    class Meta:
        label = _("Category level list")

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLString('help_text'),
        GraphQLForeignKey('category_type', CategoryLevel, required=True),
        GraphQLForeignKey('group_by_category_level', CategoryLevel, required=False),
    ]


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
    datasets = CategoryTypeDatasetsBlock()
    category_type_list = CategoryTypeLevelListBlock()
    # TODO: CategoryPageSectionBlock

    graphql_types = [
        CategoryPageAttributeTypeBlock,
        CategoryPageBodyBlock,
        CategoryPageCategoryListBlock,
        CategoryPageContactFormBlock,
        CategoryTypeDatasetsBlock,
        CategoryTypeLevelListBlock,
    ]


@register_streamfield_block
class CategoryPageAsideBlock(blocks.StreamBlock):
    attribute = CategoryPageAttributeTypeBlock()
    # TODO: CategoryPageSectionBlock

    graphql_types = [
        CategoryPageAttributeTypeBlock,
    ]
