import graphene
from graphene_django import DjangoObjectType
import graphene_django_optimizer as gql_optimizer

from actions.models import (
    Plan, Action, ActionSchedule, ActionStatus, Category, CategoryType,
)
from django_orghierarchy.models import Organization


class WithImageMixin:
    image_url = graphene.String()

    def resolve_image_url(self, info, **kwargs):
        return self.get_image_url(info.context)


class PlanNode(DjangoObjectType, WithImageMixin):
    id = graphene.ID(source='identifier')
    last_action_identifier = graphene.ID()

    class Meta:
        model = Plan
        only_fields = [
            'name', 'identifier', 'image_url', 'action_schedules', 'actions', 'category_types', 'action_statuses',
        ]


class ActionScheduleNode(DjangoObjectType):
    class Meta:
        model = ActionSchedule


class ActionStatusNode(DjangoObjectType):
    class Meta:
        model = ActionStatus


class CategoryTypeNode(DjangoObjectType):
    class Meta:
        model = CategoryType


class CategoryNode(DjangoObjectType, WithImageMixin):
    class Meta:
        model = Category


class ActionNode(DjangoObjectType, WithImageMixin):
    class Meta:
        model = Action


class OrganizationNode(DjangoObjectType):
    class Meta:
        model = Organization


class Query(graphene.ObjectType):
    plan = gql_optimizer.field(graphene.Field(PlanNode, id=graphene.ID(required=True)))
    all_plans = graphene.List(PlanNode)

    action = graphene.Field(ActionNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())
    plan_actions = graphene.List(ActionNode, plan=graphene.ID(required=True))

    def resolve_plan(self, info, **kwargs):
        qs = Plan.objects.all()
        return gql_optimizer.query(qs, info).get(identifier=kwargs['id'])

    def resolve_all_plans(self, info):
        return Plan.objects.all()

    def resolve_plan_actions(self, info, **kwargs):
        qs = Action.objects.all()
        plan = kwargs.get('plan')
        if plan is not None:
            qs = qs.filter(plan__identifier=plan)
        return gql_optimizer.query(qs, info)


schema = graphene.Schema(query=Query)
