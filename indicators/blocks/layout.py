from __future__ import annotations

from typing import Any

import graphene
from django.core.exceptions import ValidationError
from django.db.models.enums import TextChoices
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.blocks.struct_block import StructBlockValidationError

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLBoolean, GraphQLField, GraphQLForeignKey, GraphQLInt

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

from actions.blocks.choosers import CategoryLevelChooserBlock, CategoryTypeChooserBlock
from actions.blocks.filters import CategoryTypeFilterBlock
from actions.models.category import CategoryLevel, CategoryType
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
        Field(field_name='description'),
        Field(field_name='organization'),
        Field(field_name='updated_at'),
        Field(field_name='level'),
        Field(field_name='unit'),
        Field(field_name='reference'),
        Field(
            field_name='value_summary',
            custom_label=_('Value summary'),
            has_details_block=True,
            has_report_block=False,
            has_list_filters_block=False,
        ),
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
    category_level = CategoryLevelChooserBlock(
        required=False, label=_('Category level'), match=r'^list_columns-\d+', append='-value-category_type'
    )

    graphql_fields = ColumnBlockBase.graphql_fields + [
        GraphQLForeignKey('category_type', CategoryType, required=True),
        GraphQLForeignKey('category_level', CategoryLevel, required=False),
    ]

    def clean(self, value):
        ct = value.get('category_type')
        level = value.get('category_level')
        if level is not None and level.type != ct:
            raise StructBlockValidationError({'category_level': ValidationError(_('Invalid category level'))})
        return super().clean(value)


@register_streamfield_block
class IndicatorValueColumn(IndicatorListColumn):
    class IndicatorColumnValueType(TextChoices):
        LATEST = 'latest', _('Latest value')
        EARLIEST = 'earliest', _('Earliest value')
        REFERENCE = 'reference', _('Reference value')
        GOAL = 'goal', _('Goal value')

    is_normalized = blocks.BooleanBlock(required=False)
    value_type = blocks.ChoiceBlock(choices=IndicatorColumnValueType.choices, required=True)
    reference_year = blocks.IntegerBlock(required=False, help_text=_('Default reference year for reference value type'))
    hide_unit = blocks.BooleanBlock(default=False, required=False)

    graphql_fields = IndicatorListColumn.graphql_fields + [
        GraphQLBoolean('is_normalized', required=True),
        GraphQLField('value_type', graphene.Enum.from_enum(IndicatorColumnValueType), required=True),
        GraphQLInt('reference_year', required=False),
        GraphQLField('hide_unit', graphene.Boolean, required=True),
    ]

    def clean(self, value):
        result = []
        try:
            result = super().clean(value)
        except StructBlockValidationError as e:
            errors = e.block_errors
        else:
            errors = {}

        type = value.get('value_type')
        ref_year = value.get('reference_year')
        if ref_year and type != self.IndicatorColumnValueType.REFERENCE:
            errors['reference_year'] = ValidationError(_('Reference year is only allowed for reference value type'))
        if errors:
            raise StructBlockValidationError(errors)

        return result


IndicatorListColumnsStream = generate_stream_block(
    name='IndicatorListColumnsStream',
    fields=(
        'name',
        'organization',
        'level',
        ('category', IndicatorCategoryColumn()),
        ('value', IndicatorValueColumn()),
        'unit',
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


@register_streamfield_block
class IndicatorValueSummaryContentBlock(IndicatorContentBlock):
    show_reference_value = blocks.BooleanBlock(
        default=True,
        required=False,
        label=_("Show reference value"),
        help_text=_("This shows the value from the reference year."),
    )
    reference_year = blocks.IntegerBlock(
        required=False,
        help_text=_("This can be set to override the default reference year."),
    )
    show_current_value = blocks.BooleanBlock(
        default=True,
        required=False,
        label=_("Show current value"),
    )
    show_goal_value = blocks.BooleanBlock(
        default=True,
        required=False,
        label=_("Show goal value"),
    )
    show_goal_gap = blocks.BooleanBlock(
        default=True,
        required=False,
        label=_("Show goal gap"),
        help_text=_("This shows the difference between the goal and the current value."),
    )

    class Meta:
        label = _('Value summary')

    graphql_fields = [
        GraphQLBoolean('show_reference_value'),
        GraphQLInt('reference_year'),
        GraphQLBoolean('show_current_value'),
        GraphQLBoolean('show_goal_value'),
        GraphQLBoolean('show_goal_gap'),
    ]


CONTENT_BLOCK_FIELDS: tuple[str | tuple[str, blocks.Block[Any]], ...] = (
    'name',
    'description',
    'organization',
    'updated_at',
    ('category', IndicatorCategoryContentBlock()),
    'level',
    'reference',
    ('value_summary', IndicatorValueSummaryContentBlock()),
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
