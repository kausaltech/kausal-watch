import re
import pytz
import graphene
from graphene_django import DjangoObjectType
import graphene_django_optimizer as gql_optimizer

from actions.models import (
    Plan, Action, ActionSchedule, ActionStatus, Category, CategoryType,
    ActionTask, ActionImpact
)
from indicators.models import (
    Indicator, RelatedIndicator, ActionIndicator, IndicatorGraph, IndicatorLevel,
    IndicatorValue, IndicatorGoal, Unit
)
from content.models import StaticPage, BlogPost, Question
from people.models import Person
from django_orghierarchy.models import Organization


LOCAL_TZ = pytz.timezone('Europe/Helsinki')


class WithImageMixin:
    image_url = graphene.String()

    def resolve_image_url(self, info, **kwargs):
        return self.get_image_url(info.context)


class DjangoNode(DjangoObjectType):
    @classmethod
    def __init_subclass_with_meta__(cls, **kwargs):
        if 'name' not in kwargs:
            # Remove the trailing 'Node' from the object types
            kwargs['name'] = re.sub(r'Node$', '', cls.__name__)
        super().__init_subclass_with_meta__(**kwargs)

    class Meta:
        abstract = True


class UnitNode(DjangoNode):
    class Meta:
        model = Unit
        only_fields = [
            'id', 'name',
        ]


class PersonNode(DjangoNode):
    avatar_url = graphene.String()

    class Meta:
        model = Person
        only_fields = [
            'id', 'first_name', 'last_name', 'avatar_url',
        ]

    def resolve_avatar_url(self, info):
        return self.get_avatar_url()


class PlanNode(DjangoNode, WithImageMixin):
    id = graphene.ID(source='identifier')
    last_action_identifier = graphene.ID()

    static_pages = graphene.List('aplans.schema.StaticPageNode')
    blog_posts = graphene.List('aplans.schema.BlogPostNode')

    @gql_optimizer.resolver_hints(
        model_field='static_pages',
    )
    def resolve_static_pages(self, info):
        return self.static_pages.filter(is_published=True)

    @gql_optimizer.resolver_hints(
        model_field='blog_posts',
    )
    def resolve_blog_posts(self, info):
        return self.blog_posts.filter(is_published=True)

    class Meta:
        model = Plan
        only_fields = [
            'id', 'name', 'identifier', 'image_url', 'action_schedules',
            'actions', 'category_types', 'action_statuses', 'indicator_levels',
            'indicators', 'action_impacts', 'blog_posts', 'static_pages',
            'questions',
        ]


class ActionScheduleNode(DjangoNode):
    class Meta:
        model = ActionSchedule


class ActionStatusNode(DjangoNode):
    class Meta:
        model = ActionStatus


class ActionImpactNode(DjangoNode):
    class Meta:
        model = ActionImpact


class CategoryTypeNode(DjangoNode):
    class Meta:
        model = CategoryType


class CategoryNode(DjangoNode, WithImageMixin):
    class Meta:
        model = Category


class ActionTaskNode(DjangoNode):
    class Meta:
        model = ActionTask


class ActionNode(DjangoNode, WithImageMixin):
    next_action = graphene.Field('aplans.schema.ActionNode')
    previous_action = graphene.Field('aplans.schema.ActionNode')

    class Meta:
        model = Action
        only_fields = [
            'id', 'plan', 'name', 'official_name', 'identifier', 'description', 'status',
            'completion', 'schedule', 'decision_level', 'responsible_parties',
            'categories', 'indicators', 'contact_persons', 'updated_at', 'tasks',
            'related_indicators', 'impact',
        ]

    def resolve_next_action(self, info):
        return self.get_next_action()

    def resolve_previous_action(self, info):
        return self.get_previous_action()


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


class IndicatorValueNode(DjangoNode):
    time = graphene.String()

    class Meta:
        model = IndicatorValue

    def resolve_time(self, info):
        date = self.time.astimezone(LOCAL_TZ).date().isoformat()
        return date


class IndicatorGoalNode(DjangoNode):
    date = graphene.String()

    class Meta:
        model = IndicatorGoal


class IndicatorNode(DjangoNode):
    goals = graphene.List('aplans.schema.IndicatorGoalNode', plan=graphene.ID())
    level = graphene.String(plan=graphene.ID())
    actions = graphene.List('aplans.schema.ActionNode', plan=graphene.ID())

    class Meta:
        only_fields = [
            'id', 'identifier', 'name', 'description', 'time_resolution', 'unit',
            'categories', 'plans', 'levels', 'level', 'identifier', 'latest_graph', 'updated_at',
            'values', 'goals', 'latest_value', 'related_indicators', 'action_indicators',
            'actions',
        ]
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
        model_field='levels',
    )
    def resolve_level(self, info, plan):
        return self.levels.get(plan__identifier=plan).level


class OrganizationNode(DjangoNode):
    class Meta:
        model = Organization


class StaticPageNode(DjangoNode):
    @classmethod
    def get_queryset(cls, queryset, info):
        print('get queryset called')
        return queryset.filter(is_published=True)

    class Meta:
        model = StaticPage
        only_fields = [
            'id', 'title', 'slug', 'content', 'parent', 'modified_at',
        ]


class BlogPostNode(DjangoNode):
    class Meta:
        model = BlogPost
        only_fields = [
            'id', 'title', 'slug', 'published_at', 'content',
        ]


class QuestionNode(DjangoNode):
    class Meta:
        model = BlogPost
        only_fields = [
            'id', 'title', 'answer'
        ]


class Query(graphene.ObjectType):
    plan = gql_optimizer.field(graphene.Field(PlanNode, id=graphene.ID(required=True)))
    all_plans = graphene.List(PlanNode)

    action = graphene.Field(ActionNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())
    indicator = graphene.Field(IndicatorNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())

    plan_actions = graphene.List(ActionNode, plan=graphene.ID(required=True))
    plan_categories = graphene.List(CategoryNode, plan=graphene.ID(required=True))
    plan_organizations = graphene.List(OrganizationNode, plan=graphene.ID(required=True))
    plan_indicators = graphene.List(IndicatorNode, plan=graphene.ID(required=True))

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

    def resolve_plan_categories(self, info, **kwargs):
        qs = Category.objects.all()
        plan = kwargs.get('plan')
        if plan is not None:
            qs = qs.filter(type__plan__identifier=plan)
        return gql_optimizer.query(qs, info)

    def resolve_plan_organizations(self, info, **kwargs):
        qs = Organization.objects.all()
        plan = kwargs.get('plan')
        if plan is not None:
            qs = qs.filter(responsible_actions__plan__identifier=plan).distinct()
        return gql_optimizer.query(qs, info)

    def resolve_plan_indicators(self, info, **kwargs):
        qs = Indicator.objects.all()
        plan = kwargs.get('plan')
        if plan is not None:
            qs = qs.filter(levels__plan__identifier=plan).distinct()
        return gql_optimizer.query(qs, info)

    def resolve_action(self, info, **kwargs):
        obj_id = kwargs.get('id')
        identifier = kwargs.get('identifier')
        plan = kwargs.get('plan')
        if identifier and not plan:
            raise Exception("You must supply the 'plan' argument when using 'identifier'")
        qs = Action.objects.all()
        if obj_id:
            qs = qs.filter(id=obj_id)
        if identifier:
            qs = qs.filter(identifier=identifier, plan__identifier=plan)

        qs = gql_optimizer.query(qs, info)

        try:
            obj = qs.get()
        except Action.DoesNotExist:
            return None

        return obj

    def resolve_indicator(self, info, **kwargs):
        obj_id = kwargs.get('id')
        identifier = kwargs.get('identifier')
        plan = kwargs.get('plan')

        if not identifier and not obj_id:
            raise Exception("You must supply either 'id' or 'identifier'")

        qs = Indicator.objects.all()
        if obj_id:
            qs = qs.filter(id=obj_id)
        if plan:
            qs = qs.filter(levels__plan__identifier=plan).distinct()
        if identifier:
            qs = qs.filter(identifier=identifier)

        qs = gql_optimizer.query(qs, info)

        try:
            obj = qs.get()
        except Indicator.DoesNotExist:
            return None

        return obj


schema = graphene.Schema(query=Query)
