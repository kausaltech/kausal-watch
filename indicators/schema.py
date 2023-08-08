import graphene
import graphene_django_optimizer as gql_optimizer
from django.forms import ModelForm
from graphql.error import GraphQLError
from wagtail.core.rich_text import RichText

from aplans.graphql_helpers import UpdateModelInstanceMutation
from aplans.graphql_types import DjangoNode, get_plan_from_context, order_queryset, register_django_node
from aplans.utils import public_fields
from actions.schema import ScenarioNode
from indicators.models import (
    ActionIndicator, CommonIndicator, Dimension, DimensionCategory, Framework, FrameworkIndicator, Indicator,
    IndicatorDimension, IndicatorGoal, IndicatorGraph, IndicatorLevel, IndicatorValue, Quantity, RelatedCommonIndicator,
    RelatedIndicator, Unit
)
from actions.models import Action


class UnitNode(DjangoNode):
    class Meta:
        model = Unit
        fields = [
            'id', 'name', 'short_name', 'verbose_name', 'verbose_name_plural',
        ]

    @gql_optimizer.resolver_hints(
        model_field='name',
        only=('name', 'i18n')
    )
    def resolve_name(self, info):
        name = self.name_i18n
        if name is None:
            return None
        return name

    @gql_optimizer.resolver_hints(
        model_field='short_name',
        only=('short_name', 'i18n')
    )
    def resolve_short_name(self, info):
        short_name = self.short_name_i18n
        if short_name is None:
            return None
        return short_name

    @gql_optimizer.resolver_hints(
        model_field='verbose_name',
        only=('verbose_name', 'i18n')
    )
    def resolve_verbose_name(self, info):
        verbose_name = self.verbose_name_i18n
        if verbose_name is None:
            return None
        return verbose_name

    @gql_optimizer.resolver_hints(
        model_field='verbose_name_plural',
        only=('verbose_name_plural', 'i18n')
    )
    def resolve_verbose_name_plural(self, info):
        verbose_name_plural = self.verbose_name_plural_i18n
        if verbose_name_plural is None:
            return None
        return verbose_name_plural


class QuantityNode(DjangoNode):
    class Meta:
        model = Quantity
        fields = [
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
        fields = public_fields(Dimension)


class DimensionCategoryNode(DjangoNode):
    class Meta:
        model = DimensionCategory
        fields = public_fields(DimensionCategory)


class FrameworkNode(DjangoNode):
    class Meta:
        model = Framework
        fields = public_fields(Framework)


class CommonIndicatorNormalization(graphene.ObjectType):
    normalizer = graphene.Field('indicators.schema.CommonIndicatorNode')
    unit = graphene.Field(UnitNode)


class CommonIndicatorNode(DjangoNode):
    normalizations = graphene.List(CommonIndicatorNormalization)

    class Meta:
        model = CommonIndicator
        fields = public_fields(CommonIndicator)

    @gql_optimizer.resolver_hints(
        model_field='normalizations'
    )
    def resolve_normalizations(root: CommonIndicator, info):
        return root.normalizations.all()


class RelatedCommonIndicatorNode(DjangoNode):
    class Meta:
        model = RelatedCommonIndicator


class FrameworkIndicatorNode(DjangoNode):
    class Meta:
        model = FrameworkIndicator
        fields = public_fields(FrameworkIndicator)


class NormalizedValue(graphene.ObjectType):
    normalizer_id = graphene.ID()
    value = graphene.Float()


# Use for models that have an attribute `normalized_values`
class NormalizedValuesMixin:
    normalized_values = graphene.List(NormalizedValue)

    @gql_optimizer.resolver_hints(
        model_field='normalized_values',
    )
    def resolve_normalized_values(root, info):
        if not root.normalized_values:
            return []
        return [dict(normalizer_id=k, value=v) for k, v in root.normalized_values.items()]


class IndicatorValueNode(NormalizedValuesMixin, DjangoNode):
    date = graphene.String()

    class Meta:
        model = IndicatorValue
        fields = public_fields(IndicatorValue)

    def resolve_date(self: IndicatorValue, info):
        date = self.date.isoformat()
        return date


class IndicatorGoalNode(NormalizedValuesMixin, DjangoNode):
    date = graphene.String()
    scenario = graphene.Field(ScenarioNode)

    class Meta:
        model = IndicatorGoal
        fields = public_fields(IndicatorGoal) + ['scenario']

    def resolve_scenario(self: IndicatorGoal, info):
        # Scenarios are not used anymore for indicator goals. The UI
        # expects them to be, and they might be again in the future.
        return None


@register_django_node
class IndicatorNode(DjangoNode):
    ORDERABLE_FIELDS = ['updated_at']

    goals = graphene.List(IndicatorGoalNode, plan=graphene.ID(
        default_value=None,
        description=('[Deprecated] Has no effect. '
                     'The same indicator cannot have different goals '
                     'for the same organization for different plans.')
    ))
    values = graphene.List(IndicatorValueNode, include_dimensions=graphene.Boolean())
    level = graphene.String(plan=graphene.ID())
    actions = graphene.List('actions.schema.ActionNode', plan=graphene.ID())

    class Meta:
        fields = public_fields(Indicator)
        model = Indicator

    @gql_optimizer.resolver_hints(
        model_field='goals',
    )
    def resolve_goals(self, info, plan=None):
        # The plan parameter has been deprecated
        return self.goals.all()

    @gql_optimizer.resolver_hints(
        model_field='actions',
    )
    def resolve_actions(self, info, plan=None):
        qs = self.actions.visible_for_user(info.context.user)
        if plan is not None:
            qs = qs.filter(plan__identifier=plan)
        return qs

    def resolve_related_actions(self, info, plan=None):
        actions = Action.objects.visible_for_user(info.context.user)
        qs = ActionIndicator.objects.filter(action__in=actions).filter(indicator=self)
        if plan is not None:
            qs = qs.filter(indicator__plan__identifier=plan)
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

    @gql_optimizer.resolver_hints(
        model_field=('description', 'i18n'),
    )
    def resolve_description(self: Indicator, info):
        description = self.description_i18n
        if description is None:
            return None
        return RichText(description)


class IndicatorDimensionNode(DjangoNode):
    class Meta:
        model = IndicatorDimension
        fields = public_fields(IndicatorDimension)


class Query:
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
            qs = qs.filter(goals__isnull=(not has_goals)).distinct()

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
            try:
                obj_id = int(obj_id)
            except ValueError:
                raise GraphQLError("Invalid 'id'", [info])
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


class IndicatorForm(ModelForm):
    # TODO: Eventually we will want to allow updating things other than organization
    class Meta:
        model = Indicator
        fields = ['organization']


class UpdateIndicatorMutation(UpdateModelInstanceMutation):
    class Meta:
        form_class = IndicatorForm


class Mutation(graphene.ObjectType):
    update_indicator = UpdateIndicatorMutation.Field()
