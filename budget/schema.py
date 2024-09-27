from __future__ import annotations

import typing

import graphene

if typing.TYPE_CHECKING:
    from kausal_common.graphene import GQLInfo

from aplans.graphql_types import DjangoNode, register_django_node

from actions.schema import ActionNode, CategoryNode, CategoryTypeNode, PlanNode
from budget.models import (
    DataPoint,
    Dataset,
    DatasetSchema,
    DatasetSchemaDimensionCategory,
    DatasetSchemaScope,
    Dimension,
    DimensionCategory,
    DimensionScope,
)

if typing.TYPE_CHECKING:
    from actions.models.action import Action
    from actions.models.category import Category, CategoryType
    from actions.models.plan import Plan


class DimensionNode(DjangoNode):
    class Meta:
        model = Dimension
        name = 'BudgetDimension'  # clashes otherwise with type name in indicators.schema
        fields = ('uuid', 'name', 'categories', 'scopes')


class DimensionCategoryNode(DjangoNode):
    class Meta:
        model = DimensionCategory
        name = 'BudgetDimensionCategory'  # clashes otherwise with type name in indicators.schema
        fields = ('uuid', 'dimension', 'label')


class DatasetSchemaDimensionCategoryNode(DjangoNode):
    class Meta:
        model = DatasetSchemaDimensionCategory
        fields = ('order', 'category', 'schema')


class DimensionScopeNode(DjangoNode):
    scope = graphene.Field(lambda: DimensionScopeTypeNode)

    class Meta:
        model = DimensionScope
        fields = '__all__'

    @staticmethod
    def resolve_scope(root, info) -> Plan | CategoryType:
        return root.scope


class DimensionScopeTypeNode(graphene.Union):
    class Meta:
        types = (
            PlanNode, CategoryTypeNode,
        )


class DataPointNode(DjangoNode):
    value = graphene.Float()
    class Meta:
        model = DataPoint
        fields = ('uuid', 'dataset', 'date', 'value', 'dimension_categories')


class DatasetSchemaScopeNode(DjangoNode):
    scope = graphene.Field(lambda: DatasetSchemaScopeTypeNode)

    class Meta:
        model = DatasetSchemaScope
        fields = '__all__'

    @staticmethod
    def resolve_scope(root, info) -> Plan | CategoryType:
        return root.scope


class DatasetSchemaScopeTypeNode(graphene.Union):
    class Meta:
        types = (
            PlanNode, CategoryTypeNode,
        )


class DatasetScopeTypeNode(graphene.Union):
    class Meta:
        types = (
            ActionNode, CategoryNode,
        )

@register_django_node
class DatasetSchemaNode(DjangoNode):
    class Meta:
        model = DatasetSchema
        fields = ('uuid', 'time_resolution', 'unit', 'name', 'scopes', 'dimension_categories')


class DatasetNode(DjangoNode):
    scope = graphene.Field(lambda: DatasetScopeTypeNode)

    class Meta:
        model = Dataset
        fields = ('uuid', 'schema', 'data_points')

    @staticmethod
    def resolve_scope(root: Dataset, info: GQLInfo) -> Action | Category:
        return root.scope


class Query:
    pass
