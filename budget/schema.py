import graphene
from actions.schema import ActionNode, PlanNode, CategoryNode, CategoryTypeNode
from aplans.graphql_types import DjangoNode
from budget.models import (
    DataPoint, Dataset, DatasetSchema, DatasetSchemaScope, Dimension, DimensionCategory, DimensionScope
)

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


class DimensionScopeNode(DjangoNode):
    scope = graphene.Field(lambda: DimensionScopeTypeNode)

    class Meta:
        model = DimensionScope
        fields = '__all__'

    @staticmethod
    def resolve_scope(root, info):
        return root.scope


class DimensionScopeTypeNode(graphene.Union):
    class Meta:
        types = (
            PlanNode, CategoryTypeNode,
        )


class DataPointNode(DjangoNode):
    class Meta:
        model = DataPoint
        fields = ('uuid', 'dataset', 'date', 'value', 'dimension_categories')


class DatasetSchemaScopeNode(DjangoNode):
    scope = graphene.Field(lambda: DatasetSchemaScopeTypeNode)

    class Meta:
        model = DatasetSchemaScope
        fields = '__all__'

    @staticmethod
    def resolve_scope(root, info):
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
    def resolve_scope(root, info):
        return root.scope
