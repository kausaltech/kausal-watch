import re
import pytz
import graphene
import libvoikko
from graphene_django import DjangoObjectType
from graphene.utils.str_converters import to_snake_case, to_camel_case
from graphql.error import GraphQLError
import graphene_django_optimizer as gql_optimizer

from aplans.utils import public_fields
from actions.models import (
    Plan, Action, ActionSchedule, ActionStatus, Category, CategoryType,
    ActionTask, ActionImpact, ActionResponsibleParty, ActionContactPerson,
    ActionStatusUpdate, ImpactGroup, ImpactGroupAction, MonitoringQualityPoint,
    Scenario
)
from indicators.models import (
    Indicator, RelatedIndicator, ActionIndicator, IndicatorGraph, IndicatorLevel,
    IndicatorValue, IndicatorGoal, Unit, Quantity
)
from content.models import (
    StaticPage, BlogPost, Question, SiteGeneralContent
)
from people.models import Person
from django_orghierarchy.models import Organization, OrganizationClass


LOCAL_TZ = pytz.timezone('Europe/Helsinki')


try:
    voikko_fi = libvoikko.Voikko(language='fi')
    voikko_fi.setNoUglyHyphenation(True)
    voikko_fi.setMinHyphenatedWordLength(16)
except OSError:
    voikko_fi = None

_hyphenation_cache = {}


def hyphenate(s):
    if voikko_fi is None:
        return s

    tokens = voikko_fi.tokens(s)
    out = ''
    for t in tokens:
        if t.tokenTypeName != 'WORD':
            out += t.tokenText
            continue

        cached = _hyphenation_cache.get(t.tokenText, None)
        if cached is not None:
            out += cached
        else:
            val = voikko_fi.hyphenate(t.tokenText, separator='\u00ad')
            _hyphenation_cache[t.tokenText] = val
            out += val
    return out


class WithImageMixin:
    image_url = graphene.String()

    def resolve_image_url(self, info, **kwargs):
        return self.get_image_url(info.context)


class OrderableModelMixin:
    order = graphene.Int()

    @gql_optimizer.resolver_hints(
        model_field='sort_order',
    )
    def resolve_order(self, **kwargs):
        return self.sort_order


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
            'id', 'name', 'short_name', 'verbose_name', 'verbose_name_plural',
        ]


class QuantityNode(DjangoNode):
    class Meta:
        model = Quantity
        only_fields = [
            'id', 'name',
        ]


class PersonNode(DjangoNode):
    avatar_url = graphene.String()

    class Meta:
        model = Person
        only_fields = [
            'id', 'first_name', 'last_name', 'title', 'email', 'organization',
        ]

    def resolve_avatar_url(self, info):
        request = info.context
        if not request:
            return None
        return self.get_avatar_url(request)


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
        only_fields = public_fields(Plan, remove_fields=['image_url'])


class ActionScheduleNode(DjangoNode):
    class Meta:
        model = ActionSchedule


class ActionStatusNode(DjangoNode):
    class Meta:
        model = ActionStatus


class ActionResponsiblePartyNode(DjangoNode):
    class Meta:
        model = ActionResponsibleParty


class ActionContactPersonNode(DjangoNode):
    class Meta:
        model = ActionContactPerson


class ActionImpactNode(DjangoNode):
    class Meta:
        model = ActionImpact


class ActionStatusUpdateNode(DjangoNode):
    class Meta:
        model = ActionStatusUpdate
        only_fields = [
            'id', 'action', 'title', 'date', 'author', 'content'
        ]


class CategoryTypeNode(DjangoNode):
    class Meta:
        model = CategoryType


class CategoryNode(DjangoNode, WithImageMixin):
    class Meta:
        model = Category


class ScenarioNode(DjangoNode):
    class Meta:
        model = Scenario
        only_fields = public_fields(Scenario)


class ImpactGroupNode(DjangoNode, WithImageMixin):
    name = graphene.String()

    class Meta:
        model = ImpactGroup
        only_fields = public_fields(ImpactGroup, remove_fields=['name'])


class ImpactGroupActionNode(DjangoNode, WithImageMixin):
    class Meta:
        model = ImpactGroupAction


class MonitoringQualityPointNode(DjangoNode):
    name = graphene.String()
    description_yes = graphene.String()
    description_no = graphene.String()

    class Meta:
        model = MonitoringQualityPoint


class ActionTaskNode(DjangoNode):
    class Meta:
        model = ActionTask


class ActionNode(DjangoNode, WithImageMixin):
    ORDERABLE_FIELDS = ['updated_at', 'identifier']

    name = graphene.String(hyphenated=graphene.Boolean())
    categories = graphene.List(CategoryNode, category_type=graphene.ID())
    next_action = graphene.Field('aplans.schema.ActionNode')
    previous_action = graphene.Field('aplans.schema.ActionNode')

    class Meta:
        model = Action
        only_fields = Action.public_fields

    def resolve_next_action(self, info):
        return self.get_next_action()

    def resolve_previous_action(self, info):
        return self.get_previous_action()

    @gql_optimizer.resolver_hints(
        model_field='name',
    )
    def resolve_name(self, info, hyphenated=False):
        name = self.name
        if name is None:
            return None
        if hyphenated:
            name = hyphenate(name)
        return name

    @gql_optimizer.resolver_hints(
        model_field='categories',
    )
    def resolve_categories(self, info, category_type=None):
        qs = self.categories.all()
        if category_type is not None:
            qs = qs.filter(type__identifier=category_type)
        return qs


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
    date = graphene.String()

    class Meta:
        model = IndicatorValue

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

    goals = graphene.List('aplans.schema.IndicatorGoalNode', plan=graphene.ID())
    level = graphene.String(plan=graphene.ID())
    actions = graphene.List('aplans.schema.ActionNode', plan=graphene.ID())

    class Meta:
        only_fields = [
            'id', 'identifier', 'name', 'description', 'time_resolution', 'unit', 'quantity',
            'categories', 'plans', 'levels', 'identifier', 'latest_graph', 'updated_at',
            'values', 'goals', 'latest_value', 'related_actions',
            'actions', 'related_causes', 'related_effects',
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
        try:
            obj = self.levels.get(plan__identifier=plan)
        except IndicatorLevel.DoesNotExist:
            return None
        return obj.level


class OrganizationClassNode(DjangoNode):
    class Meta:
        model = OrganizationClass


class OrganizationNode(DjangoNode):
    ancestors = graphene.List('aplans.schema.OrganizationNode')

    def resolve_ancestors(self, info):
        return self.get_ancestors()

    class Meta:
        model = Organization
        only_fields = [
            'id', 'abbreviation', 'parent', 'name', 'classification', 'distinct_name',
        ]


class StaticPageNode(DjangoNode, WithImageMixin):
    @classmethod
    def get_queryset(cls, queryset, info):
        return queryset.filter(is_published=True)

    class Meta:
        model = StaticPage
        only_fields = [
            'id', 'title', 'name', 'slug', 'tagline', 'content', 'parent', 'modified_at',
            'questions', 'top_menu', 'footer',
        ]


class BlogPostNode(DjangoNode, WithImageMixin):
    class Meta:
        model = BlogPost
        only_fields = [
            'id', 'title', 'slug', 'published_at', 'content',
        ]


class QuestionNode(DjangoNode):
    class Meta:
        model = Question
        only_fields = [
            'id', 'title', 'answer'
        ]


class SiteGeneralContentNode(DjangoNode):
    class Meta:
        model = SiteGeneralContent
        only_fields = public_fields(SiteGeneralContent)


def order_queryset(qs, node_class, order_by):
    if order_by is None:
        return qs

    orderable_fields = node_class.ORDERABLE_FIELDS
    if order_by[0] == '-':
        desc = '-'
        order_by = order_by[1:]
    else:
        desc = ''
    order_by = to_snake_case(order_by)
    if order_by not in orderable_fields:
        raise ValueError('Only orderable fields are: %s' % ', '.join(
            [to_camel_case(x) for x in orderable_fields]
        ))
    qs = qs.order_by(desc + order_by)
    return qs


class Query(graphene.ObjectType):
    plan = gql_optimizer.field(graphene.Field(PlanNode, id=graphene.ID(required=True)))
    all_plans = graphene.List(PlanNode)

    action = graphene.Field(ActionNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())
    indicator = graphene.Field(IndicatorNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())
    person = graphene.Field(PersonNode, id=graphene.ID(required=True))
    static_page = graphene.Field(StaticPageNode, plan=graphene.ID(required=True), slug=graphene.ID(required=True))

    plan_actions = graphene.List(
        ActionNode, plan=graphene.ID(required=True), first=graphene.Int(),
        order_by=graphene.String()
    )
    plan_categories = graphene.List(CategoryNode, plan=graphene.ID(required=True), category_type=graphene.ID())
    organizations = graphene.List(
        OrganizationNode, plan=graphene.ID(), with_ancestors=graphene.Boolean(default_value=False)
    )
    plan_indicators = graphene.List(
        IndicatorNode, plan=graphene.ID(required=True), first=graphene.Int(),
        order_by=graphene.String(), has_data=graphene.Boolean(), has_goals=graphene.Boolean(),
    )

    def resolve_plan(self, info, **kwargs):
        qs = Plan.objects.all()
        try:
            plan = gql_optimizer.query(qs, info).get(identifier=kwargs['id'])
        except Plan.DoesNotExist:
            return None
        return plan

    def resolve_all_plans(self, info):
        return Plan.objects.all()

    def resolve_plan_actions(self, info, plan, first=None, order_by=None, **kwargs):
        qs = Action.objects.all()
        qs = qs.filter(plan__identifier=plan)
        qs = order_queryset(qs, ActionNode, order_by)
        if first is not None:
            qs = qs[0:first]

        return gql_optimizer.query(qs, info)

    def resolve_categories(self, info, category_type):
        qs = self.categories
        if type is not None:
            qs = qs.filter(type__identifier=type)
        return qs

    def resolve_plan_categories(self, info, **kwargs):
        qs = Category.objects.all()

        plan = kwargs.get('plan')
        if plan is not None:
            qs = qs.filter(type__plan__identifier=plan)

        category_type = kwargs.get('category_type')
        if category_type is not None:
            qs = qs.filter(type__identifier=category_type)

        return gql_optimizer.query(qs, info)

    def resolve_organizations(self, info, plan, with_ancestors, **kwargs):
        qs = Organization.objects.all()
        if plan is not None:
            qs = qs.filter(responsible_actions__action__plan__identifier=plan).distinct()

        if with_ancestors:
            # Retrieving ancestors for a queryset doesn't seem to work,
            # so iterate over parents until we have a set of model IDs
            # for all children and their ancestors.
            if plan is None:
                raise GraphQLError("withAncestors can only be used when 'plan' is set", [info])
            all_ids = set()
            while True:
                vals = qs.values_list('id', 'parent')
                ids = set((val[0] for val in vals))
                parent_ids = set((val[1] for val in vals))
                all_ids.update(ids)
                if parent_ids.issubset(all_ids):
                    break
                qs = Organization.objects.filter(id__in=parent_ids)
            qs = Organization.objects.filter(id__in=all_ids)

        return gql_optimizer.query(qs, info)

    def resolve_plan_indicators(
        self, info, plan, first=None, order_by=None, has_data=None,
        has_goals=None, **kwargs
    ):
        qs = Indicator.objects.all()
        qs = qs.filter(levels__plan__identifier=plan).distinct()

        if has_data is not None:
            qs = qs.filter(latest_value__isnull=not has_data)

        if has_goals is not None:
            qs = qs.filter(goals__plan__identifier=plan).distinct()

        qs = order_queryset(qs, IndicatorNode, order_by)
        if first is not None:
            qs = qs[0:first]

        return gql_optimizer.query(qs, info)

    def resolve_action(self, info, **kwargs):
        obj_id = kwargs.get('id')
        identifier = kwargs.get('identifier')
        plan = kwargs.get('plan')
        if identifier and not plan:
            raise GraphQLError("You must supply the 'plan' argument when using 'identifier'", [info])
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

    def resolve_person(self, info, **kwargs):
        qs = Person.objects.all()
        obj_id = kwargs.get('id')
        qs = qs.filter(id=obj_id)
        try:
            obj = qs.get()
        except Person.DoesNotExist:
            return None

        return obj

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
            qs = qs.filter(levels__plan__identifier=plan).distinct()
        if identifier:
            qs = qs.filter(identifier=identifier)

        qs = gql_optimizer.query(qs, info)

        try:
            obj = qs.get()
        except Indicator.DoesNotExist:
            return None

        return obj

    def resolve_static_page(self, info, **kwargs):
        slug = kwargs.get('slug')
        plan = kwargs.get('plan')

        if not slug or not plan:
            raise GraphQLError("You must supply both 'slug' and 'plan'", [info])

        qs = StaticPage.objects.all()
        qs = qs.filter(slug=slug, plan__identifier=plan)
        qs = gql_optimizer.query(qs, info)

        try:
            obj = qs.get()
        except StaticPage.DoesNotExist:
            return None

        return obj


schema = graphene.Schema(query=Query)
