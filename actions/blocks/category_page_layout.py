from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString

from kausal_common.datasets.models import DatasetSchema

from actions.blocks.action_content_blocks import BaseContactFormBlock, BaseDatasetsBlock
from actions.blocks.choosers import (
    CategoryAttributeTypeChooserBlock,
    CategoryTypeDatasetSchemaChooserBlock,
)
from actions.models.attributes import AttributeType
from audit_logging.blocks import ChangeLogMessageBlock


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
        label = _('Contact form')


@register_streamfield_block
class CategoryTypeDatasetsBlock(BaseDatasetsBlock):
    dataset_schema = CategoryTypeDatasetSchemaChooserBlock(required=True)

    graphql_fields = BaseDatasetsBlock.graphql_fields + [
        GraphQLForeignKey('dataset_schema', DatasetSchema, required=True),
    ]


@register_streamfield_block
class CategoryPageProgressBlock(blocks.StructBlock):
    basis = blocks.ChoiceBlock(
        label=_('Basis'),
        choices=[
            ('implementation_phase', _('Implementation phase')),
            ('status', _('Status')),
        ],
    )

    class Meta:
        label = _('Progress')


@register_streamfield_block
class PathsNodeSummaryBlock(blocks.StructBlock):
    heading = blocks.CharBlock(
        required=False,
        help_text=_('What heading should be used in the public UI for the Paths node summary?'),
        default='',
        label=_('Heading'),
    )
    paths_target_node_id = blocks.CharBlock(
        max_length=200,
        required=False,
        verbose_name=_('Kausal Paths target node ID'),
        help_text=_(
            'Kausal Paths target node ID used to calculate action impacts. If not set, the default outcome node will be used.'
        ),
    )

    class Meta:
        label = _('Paths node summary')

    graphql_fields = [
        GraphQLString('heading', required=False),
        GraphQLString('paths_target_node_id', required=False),
    ]


@register_streamfield_block
class CategoryPageMainTopBlock(blocks.StreamBlock):
    attribute = CategoryPageAttributeTypeBlock()
    progress = CategoryPageProgressBlock()
    paths_node_summary = PathsNodeSummaryBlock()

    graphql_types = [
        CategoryPageAttributeTypeBlock,
        CategoryPageProgressBlock,
        PathsNodeSummaryBlock,
    ]


@register_streamfield_block
class CategoryPageMainBottomBlock(blocks.StreamBlock):
    attribute = CategoryPageAttributeTypeBlock()
    body = CategoryPageBodyBlock()
    category_list = CategoryPageCategoryListBlock()
    contact_form = CategoryPageContactFormBlock()
    datasets = CategoryTypeDatasetsBlock()
    change_log_message = ChangeLogMessageBlock()
    # TODO: CategoryPageSectionBlock

    graphql_types = [
        CategoryPageAttributeTypeBlock,
        CategoryPageBodyBlock,
        CategoryPageCategoryListBlock,
        CategoryPageContactFormBlock,
        CategoryTypeDatasetsBlock,
        ChangeLogMessageBlock,
    ]


@register_streamfield_block
class CategoryPageAsideBlock(blocks.StreamBlock):
    attribute = CategoryPageAttributeTypeBlock()
    # TODO: CategoryPageSectionBlock

    graphql_types = [
        CategoryPageAttributeTypeBlock,
    ]
