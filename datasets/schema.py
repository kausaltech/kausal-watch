from __future__ import annotations

import graphene

from kausal_common.datasets.models import (
    DataPoint,
    Dataset,
    DatasetSchema,
    DatasetSchemaDimensionCategory,
    DatasetSchemaScope,
    Dimension,
    DimensionCategory,
    DimensionScope,
)
from kausal_common.datasets.schema import (
    DataPointNode as BaseDataPointNode,
    DatasetNode as BaseDatasetNode,
    DatasetSchemaDimensionCategoryNode as BaseDatasetSchemaDimensionCategoryNode,
    DatasetSchemaNode as BaseDatasetSchemaNode,
    DatasetSchemaScopeNode as BaseDatasetSchemaScopeNode,
    DatasetSchemaScopeTypeNode as BaseDatasetSchemaScopeTypeNode,
    DatasetScopeTypeNode as BaseDatasetScopeTypeNode,
    DimensionCategoryNode as BaseDimensionCategoryNode,
    DimensionNode as BaseDimensionNode,
    DimensionScopeNode as BaseDimensionScopeNode,
    DimensionScopeTypeNode as BaseDimensionScopeTypeNode,
)

from aplans.graphql_types import DjangoNode, register_django_node

from actions.schema import ActionNode, CategoryNode, CategoryTypeNode, PlanNode

# if typing.TYPE_CHECKING:
#     from actions.models.action import Action
#     from actions.models.category import Category, CategoryType
#     from actions.models.plan import Plan


class DimensionNode(BaseDimensionNode, DjangoNode):
    class Meta:
        model = Dimension
        name = 'DatasetsDimension'  # clashes otherwise with type name in indicators.schema
        fields = ('uuid', 'name', 'categories', 'scopes')


class DimensionCategoryNode(BaseDimensionCategoryNode, DjangoNode):
    class Meta:
        model = DimensionCategory
        name = 'DatasetsDimensionCategory'  # clashes otherwise with type name in indicators.schema
        fields = ('uuid', 'dimension', 'label')


class DatasetSchemaDimensionCategoryNode(BaseDatasetSchemaDimensionCategoryNode, DjangoNode):
    class Meta:
        model = DatasetSchemaDimensionCategory
        fields = ('order', 'category', 'schema')



class DimensionScopeNode(BaseDimensionScopeNode, DjangoNode):
    scope = graphene.Field(lambda: DimensionScopeTypeNode)

    class Meta:
        model = DimensionScope
        fields = '__all__'


class DimensionScopeTypeNode(BaseDimensionScopeTypeNode):
    class Meta:
        types = (PlanNode, CategoryTypeNode)



class DataPointNode(BaseDataPointNode, DjangoNode):
    class Meta:
        model = DataPoint
        fields = ('uuid', 'dataset', 'date', 'value', 'dimension_categories')


class DatasetSchemaScopeNode(BaseDatasetSchemaScopeNode, DjangoNode):
    scope = graphene.Field(lambda: DatasetSchemaScopeTypeNode)

    class Meta:
        model = DatasetSchemaScope
        fields = '__all__'


class DatasetSchemaScopeTypeNode(BaseDatasetSchemaScopeTypeNode):
    class Meta:
        types = (
            PlanNode, CategoryTypeNode,
        )


class DatasetScopeTypeNode(BaseDatasetScopeTypeNode):
    class Meta:
        types = (
            ActionNode, CategoryNode,
        )

@register_django_node
class DatasetSchemaNode(BaseDatasetSchemaNode, DjangoNode):
    class Meta:
        model = DatasetSchema
        fields = ('uuid', 'time_resolution', 'unit', 'name', 'scopes', 'dimension_categories')


class DatasetNode(BaseDatasetNode, DjangoNode):
    scope = graphene.Field(lambda: DatasetScopeTypeNode)
    class Meta:
        model = Dataset
        fields = ('uuid', 'schema', 'data_points')


class Query:
    pass
