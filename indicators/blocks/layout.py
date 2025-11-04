from __future__ import annotations

from typing import Any

import graphene
from django.db.models.enums import TextChoices
from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLBoolean, GraphQLField, GraphQLForeignKey

from kausal_common.blocks.base import (
    ColumnBlockBase,
    DashboardColumnInterface,
    FilterBlockBase,
    FilterBlockInterface,
    GeneralFieldBlockBase,
    GeneralFieldBlockInterface,
)
from kausal_common.blocks.fields import FieldBlockMetaInterface
from kausal_common.blocks.registry import FieldBlockContext, FieldContextConfig, ModelFieldProperties, ModelFieldRegistry
from kausal_common.blocks.stream_block import generate_stream_block

from actions.blocks.choosers import CategoryTypeChooserBlock
from actions.blocks.filters import CategoryTypeFilterBlock
from actions.models.category import CategoryType
from indicators.models import Indicator

from . import generated

indicator_registry: ModelFieldRegistry[Indicator]


class IndicatorListColumnInterface(DashboardColumnInterface):
    source_field = graphene.Field(
        lambda: indicator_registry.get_field_enum_for_context(FieldBlockContext.DASHBOARD), required=False
    )

@register_streamfield_block
class IndicatorListColumn(ColumnBlockBase):
    graphql_interfaces = [*ColumnBlockBase.graphql_interfaces, IndicatorListColumnInterface]


class IndicatorContentBlockInterface(GeneralFieldBlockInterface):
    source_field = graphene.Field(
        lambda: indicator_registry.get_field_enum_for_context(FieldBlockContext.DETAILS), required=False
    )

@register_streamfield_block
class IndicatorContentBlock(GeneralFieldBlockBase):
    graphql_interfaces = [FieldBlockMetaInterface, IndicatorContentBlockInterface]


class IndicatorFilterBlockInterface(FilterBlockInterface):
    source_field = graphene.Field(
        lambda: indicator_registry.get_field_enum_for_context(FieldBlockContext.LIST_FILTERS), required=False
    )

@register_streamfield_block
class IndicatorFilterBlock(FilterBlockBase):
    graphql_interfaces = [IndicatorFilterBlockInterface]


indicator_registry = ModelFieldRegistry(
    model=Indicator,
    target_module=generated,
    contexts=[
        FieldContextConfig(
            context=FieldBlockContext.DASHBOARD,
            block_base_class=IndicatorListColumn,
        ),
        FieldContextConfig(
            context=FieldBlockContext.REPORT,
            block_base_class=IndicatorContentBlock,
        ),
        FieldContextConfig(
            context=FieldBlockContext.DETAILS,
            block_base_class=IndicatorContentBlock,
        ),
        FieldContextConfig(
            context=FieldBlockContext.LIST_FILTERS,
            block_base_class=IndicatorFilterBlock,
        ),
    ],
    no_type_autogen=True,
)


def register(*field_props: ModelFieldProperties):
    for field_prop in field_props:
        indicator_registry.register(field_prop)


Field = ModelFieldProperties


def initialize():
    register(
        Field(field_name='name'),
        Field(field_name='organization'),
        Field(field_name='updated_at'),
        Field(field_name='level'),
        Field(
            field_name='causality_nav',
            has_details_block=True,
            has_report_block=False,
            has_list_filters_block=False,
            custom_label=_('Causality navigation'),
        ),
        Field(
            field_name='visualization',
            custom_label=_('Indicator visualization'),
            has_details_block=True,
            has_report_block=False,
            has_list_filters_block=False,
        ),
        Field(
            field_name='connected_actions',
            custom_label=_('Connected actions'),
            has_details_block=True,
            has_report_block=False,
            has_list_filters_block=False,
        ),
    )
    indicator_registry.finalize()


initialize()


@register_streamfield_block
class IndicatorCategoryColumn(ColumnBlockBase):
    category_type = CategoryTypeChooserBlock(required=True)

    graphql_fields = ColumnBlockBase.graphql_fields + [
        GraphQLForeignKey('category_type', CategoryType, required=True),
    ]


@register_streamfield_block
class IndicatorValueColumn(IndicatorListColumn):
    class IndicatorColumnValueType(TextChoices):
        LATEST = 'latest', _('Latest value')
        EARLIEST = 'earliest', _('Earliest value')
        GOAL = 'goal', _('Goal value')

    is_normalized = blocks.BooleanBlock(required=False)
    value_type = blocks.ChoiceBlock(choices=IndicatorColumnValueType.choices, required=True)

    graphql_fields = IndicatorListColumn.graphql_fields + [
        GraphQLBoolean('is_normalized', required=True),
        GraphQLField('value_type', graphene.Enum.from_enum(IndicatorColumnValueType), required=True),
    ]


IndicatorListColumnsStream = generate_stream_block(
    name='IndicatorListColumnsStream',
    fields=(
        'name',
        'organization',
        'level',
        ('category', IndicatorCategoryColumn()),
        ('value', IndicatorValueColumn()),
        'updated_at',
    ),
    block_context=FieldBlockContext.DASHBOARD,
    field_registry=indicator_registry,
)


def get_organization_node():
    from orgs.schema import OrganizationNode

    return OrganizationNode


IndicatorListFilterStream = generate_stream_block(
    name='IndicatorListFilterStream',
    fields=(
        'organization',
        'level',
        ('category', CategoryTypeFilterBlock()),
    ),
    block_context=FieldBlockContext.LIST_FILTERS,
    field_registry=indicator_registry,
)


@register_streamfield_block
class IndicatorCategoryContentBlock(IndicatorContentBlock):
    category_type = CategoryTypeChooserBlock(required=True)

    graphql_fields = [
        *IndicatorContentBlock.graphql_fields,
        GraphQLForeignKey('category_type', CategoryType, required=True),
    ]

    class Meta:
        label = _('Category')


CONTENT_BLOCK_FIELDS: tuple[str | tuple[str, blocks.Block[Any]], ...] = (
    'name',
    'organization',
    'updated_at',
    ('category', IndicatorCategoryContentBlock()),
    'level',
    'visualization',
    'connected_actions',
    'causality_nav',
)

IndicatorAsideContentStream = generate_stream_block(
    name='IndicatorAsideContentStream',
    fields=CONTENT_BLOCK_FIELDS,
    block_context=FieldBlockContext.DETAILS,
    field_registry=indicator_registry,
)

IndicatorMainContentStream = generate_stream_block(
    name='IndicatorMainContentStream',
    fields=CONTENT_BLOCK_FIELDS,
    block_context=FieldBlockContext.DETAILS,
    field_registry=indicator_registry,
)
