from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, cast

import strawberry
import strawberry_django

from grapple.registry import registry as grapple_registry

from kausal_common.datasets.models import (
    DataPoint,
    Dataset,
    DatasetMetric,
    DatasetSchema,
    DatasetSchemaDimension,
    DatasetSchemaScope,
    Dimension,
    DimensionCategory,
    DimensionScope,
)
from kausal_common.strawberry.registry import register_strawberry_type

from actions.schema import ActionNode, CategoryNode, CategoryTypeNode, PlanNode
from indicators.schema import IndicatorNode

if TYPE_CHECKING:
    from strawberry import auto

DimensionScopeType = Annotated[
    PlanNode | CategoryTypeNode,
    strawberry.union('DimensionScopeType'),
]

DatasetSchemaScopeType = Annotated[
    PlanNode | CategoryTypeNode,
    strawberry.union('DatasetSchemaScopeType'),
]

DatasetScopeType = Annotated[
    ActionNode | CategoryNode,
    strawberry.union('DatasetScopeType'),
]


@register_strawberry_type
@strawberry_django.type(Dimension, name='DatasetsDimension')
class DimensionNode:
    uuid: auto
    name: auto
    categories: list[DimensionCategoryNode]
    scopes: list[DimensionScopeNode]


@register_strawberry_type
@strawberry_django.type(DimensionCategory, name='DatasetsDimensionCategory')
class DimensionCategoryNode:
    uuid: auto
    dimension: DimensionNode
    label: auto


@register_strawberry_type
@strawberry_django.type(DimensionScope, name='DimensionScope')
class DimensionScopeNode:
    @strawberry_django.field
    def scope(self: DimensionScope) -> DimensionScopeType | None:
        return cast('DimensionScopeType', self.scope)


@register_strawberry_type
@strawberry_django.type(DataPoint, name='DataPoint')
class DataPointNode:
    uuid: auto
    dataset: DatasetNode
    date: auto
    dimension_categories: list[DimensionCategoryNode]

    @strawberry_django.field
    def value(self: DataPoint) -> float | None:
        return float(self.value) if self.value is not None else None


@register_strawberry_type
@strawberry_django.type(DatasetSchemaScope, name='DatasetSchemaScope')
class DatasetSchemaScopeNode:
    @strawberry_django.field
    def scope(self: DatasetSchemaScope) -> DatasetSchemaScopeType | None:
        return cast('DatasetSchemaScopeType', self.scope)


@register_strawberry_type
@strawberry_django.type(DatasetSchemaDimension, name='DatasetSchemaDimension')
class DatasetSchemaDimensionNode:
    order: auto
    dimension: DimensionNode
    schema: DatasetSchemaNode


@register_strawberry_type
@strawberry_django.type(DatasetMetric, name='DatasetMetricNode')
class DatasetMetricNode:
    uuid: auto
    schema: DatasetSchemaNode
    name: auto
    label: auto
    unit: auto
    order: auto


@register_strawberry_type
@strawberry_django.type(DatasetSchema, name='DatasetSchema')
class DatasetSchemaNode:
    uuid: auto
    name: auto
    scopes: list[DatasetSchemaScopeNode]
    dimensions: list[DatasetSchemaDimensionNode]
    metrics: list[DatasetMetricNode]

    @strawberry_django.field
    def time_resolution(self: DatasetSchema) -> str:
        return self.time_resolution.upper()


# Register in Grapple's django_models so PlanDatasetsBlock can find it
grapple_registry.django_models[DatasetSchema] = DatasetSchemaNode


@register_strawberry_type
@strawberry_django.type(Dataset, name='Dataset')
class DatasetNode:
    uuid: auto
    schema: DatasetSchemaNode | None
    data_points: list[DataPointNode]

    @strawberry_django.field
    def scope(self: Dataset) -> DatasetScopeType | None:
        return cast('DatasetScopeType', self.scope)


class Query:
    pass
