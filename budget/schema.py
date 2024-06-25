import graphene
from actions.schema import ActionNode, CategoryNode, PlanNode, CategoryTypeNode
from aplans.graphql_types import DjangoNode
from budget.models import DataPoint, Dataset, DatasetScope, Dimension, DimensionCategory, DimensionScope

class DatasetDimensionNode(DjangoNode):
    categories = graphene.List(lambda: DatasetDimensionCategoryNode)

    class Meta:
        model = Dimension
        fields = ('id', 'uuid', 'name')

    @staticmethod
    def resolve_categories(root, info):
        return root.categories.all()

class DatasetDimensionCategoryNode(DjangoNode):
    class Meta:
        model = DimensionCategory
        fields = ('id', 'uuid', 'dimension', 'label')

class DatasetDimensionScopeNode(DjangoNode):
    scope = graphene.Field(lambda: DatasetDimensionScopeTypeNode)

    class Meta:
        model = DimensionScope
        fields = '__all__'

    @staticmethod
    def resolve_scope(root, info):
        return root.scope

class DatasetDimensionScopeTypeNode(graphene.Union):
    class Meta:
        types = (
            PlanNode, CategoryTypeNode,
        )

class DataPointNode(DjangoNode):
    dimension_categories = graphene.List(DatasetDimensionCategoryNode)

    class Meta:
        model = DataPoint
        fields = ('uuid', 'dataset', 'date', 'value')

    @staticmethod
    def resolve_dimension_categories(root, info):
        return root.dimension_categories.all()

class DatasetScopeNode(DjangoNode):
    scope = graphene.Field(lambda: DatasetScopeTypeNode)

    class Meta:
        model = DatasetScope
        fields = '__all__'

    @staticmethod
    def resolve_scope(root, info):
        return root.scope

class DatasetScopeTypeNode(graphene.Union):
    class Meta:
        types = (
            ActionNode, CategoryNode,
        )

class DatasetNode(DjangoNode):
    data_points = graphene.List(DataPointNode)
    scopes = graphene.List(DatasetScopeNode)

    class Meta:
        model = Dataset
        fields = ('uuid', 'time_resolution', 'unit')

    @staticmethod
    def resolve_data_points(root, info):
        return root.data_points.order_by('date').all()

    @staticmethod
    def resolve_scopes(root, info):
        return DatasetScope.objects.filter(dataset=root)
