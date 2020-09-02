import graphene
import graphene_django_optimizer as gql_optimizer
from graphql.error import GraphQLError

from aplans.graphql_types import DjangoNode, get_plan_from_context, order_queryset
from aplans.utils import public_fields
from indicators.models import (
    ActionIndicator, CommonIndicator, Dimension, DimensionCategory, Framework, FrameworkIndicator, Indicator,
    IndicatorDimension, IndicatorGoal, IndicatorGraph, IndicatorLevel, IndicatorValue, Quantity, RelatedIndicator, Unit
)


class UnitNode(DjangoNode):
    class Meta:
        model = Unit
        only_fields = [
            'id', 'name', 'short_name', 'verbose_name', 'verbose_name_plural',
        ]


class QuantityNode(DjangoNode):
    class Meta:
        model = Quantity
        only_fields = [
            'id', 'name',
        ]


class RelatedIndicatorNode(DjangoNode):
    class Meta:
        model = RelatedIndicator


class ActionIndicatorNode(DjangoNode):
    class Meta:
        model = ActionIndicator


class IndicatorGraphNode(DjangoNode):
    class Meta:
        model = IndicatorGraph


class IndicatorLevelNode(DjangoNode):
    class Meta:
        model = IndicatorLevel


class DimensionNode(DjangoNode):
    class Meta:
        model = Dimension
        only_fields = public_fields(Dimension)


class DimensionCategoryNode(DjangoNode):
    class Meta:
        model = DimensionCategory
        only_fields = public_fields(DimensionCategory)


class FrameworkNode(DjangoNode):
    class Meta:
        model = Framework
        only_fields = public_fields(Framework)


class CommonIndicatorNode(DjangoNode):
    class Meta:
        model = CommonIndicator
        only_fields = public_fields(CommonIndicator)


class FrameworkIndicatorNode(DjangoNode):
    class Meta:
        model = FrameworkIndicator
        only_fields = public_fields(FrameworkIndicator)


class IndicatorValueNode(DjangoNode):
    date = graphene.String()

    class Meta:
        model = IndicatorValue
        only_fields = public_fields(IndicatorValue)

    def resolve_date(self, info):
        date = self.date.isoformat()
        return date


class IndicatorGoalNode(DjangoNode):
    date = graphene.String()

    class Meta:
        model = IndicatorGoal
        only_fields = public_fields(IndicatorGoal)


class IndicatorNode(DjangoNode):
    ORDERABLE_FIELDS = ['updated_at']

    goals = graphene.List(IndicatorGoalNode, plan=graphene.ID())
    values = graphene.List(IndicatorValueNode, include_dimensions=graphene.Boolean())
    level = graphene.String(plan=graphene.ID())
    actions = graphene.List('aplans.schema.ActionNode', plan=graphene.ID())

    class Meta:
        only_fields = public_fields(Indicator)
        model = Indicator

    @gql_optimizer.resolver_hints(
        model_field='goals',
    )
    def resolve_goals(self, info, plan=None):
        qs = self.goals.all()
        if plan is not None:
            qs = qs.filter(plan__identifier=plan)
        return qs

    @gql_optimizer.resolver_hints(
        model_field='actions',
    )
    def resolve_actions(self, info, plan=None):
        qs = self.actions.all()
        if plan is not None:
            qs = qs.filter(plan__identifier=plan)
        return qs

    @gql_optimizer.resolver_hints(
        model_field='values',
    )
    def resolve_values(self, info, include_dimensions=None):
        qs = self.values.all()
        if not include_dimensions:
            qs = qs.filter(categories__isnull=True).distinct()
        return qs

    @gql_optimizer.resolver_hints(
        model_field='levels',
    )
    def resolve_level(self, info, plan):
        try:
            obj = self.levels.get(plan__identifier=plan)
        except IndicatorLevel.DoesNotExist:
            return None
        return obj.level


class IndicatorDimensionNode(DjangoNode):
    class Meta:
        model = IndicatorDimension
        only_fields = public_fields(IndicatorDimension)


class Query(graphene.ObjectType):
    indicator = graphene.Field(IndicatorNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())
    plan_indicators = graphene.List(
        IndicatorNode, plan=graphene.ID(required=True), first=graphene.Int(),
        order_by=graphene.String(), has_data=graphene.Boolean(), has_goals=graphene.Boolean(),
    )

    def resolve_plan_indicators(
        self, info, plan, first=None, order_by=None, has_data=None,
        has_goals=None, **kwargs
    ):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        qs = Indicator.objects.all()
        qs = qs.filter(levels__plan=plan_obj).distinct()

        if has_data is not None:
            qs = qs.filter(latest_value__isnull=not has_data)

        if has_goals is not None:
            qs = qs.filter(goals__plan__identifier=plan).distinct()

        qs = order_queryset(qs, IndicatorNode, order_by)
        if first is not None:
            qs = qs[0:first]

        return gql_optimizer.query(qs, info)

    def resolve_indicator(self, info, **kwargs):
        obj_id = kwargs.get('id')
        identifier = kwargs.get('identifier')
        plan = kwargs.get('plan')

        if not identifier and not obj_id:
            raise GraphQLError("You must supply either 'id' or 'identifier'", [info])

        qs = Indicator.objects.all()
        if obj_id:
            qs = qs.filter(id=obj_id)
        if plan:
            plan_obj = get_plan_from_context(info, plan)
            if not plan_obj:
                return None
            qs = qs.filter(levels__plan=plan_obj).distinct()
        if identifier:
            qs = qs.filter(identifier=identifier)

        qs = gql_optimizer.query(qs, info)

        try:
            obj = qs.get()
        except Indicator.DoesNotExist:
            return None

        return obj