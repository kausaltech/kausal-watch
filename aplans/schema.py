import graphene
import graphene_django_optimizer as gql_optimizer
import libvoikko
import pytz
from django_orghierarchy.models import Organization, OrganizationClass
from graphql.error import GraphQLError
from graphql.type import (
    DirectiveLocation, GraphQLArgument, GraphQLDirective, GraphQLNonNull, GraphQLString, specified_directives
)
from wagtail.core.rich_text import RichText

from actions.models import (
    Action, ActionContactPerson, ActionImpact, ActionResponsibleParty, ActionSchedule, ActionStatus, ActionStatusUpdate,
    ActionTask, Category, CategoryType, ImpactGroup, ImpactGroupAction, MonitoringQualityPoint, Plan, Scenario
)
from aplans.utils import public_fields
from content.models import BlogPost, Question, SiteGeneralContent, StaticPage
from indicators import schema as indicators_schema
from pages import schema as pages_schema
from pages.models import AplansPage
from people.models import Person

from .graphql_types import DjangoNode, get_plan_from_context, order_queryset, set_active_plan

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
    image_url = graphene.String(size=graphene.String())

    def resolve_image_url(self, info, size=None, **kwargs):
        request = info.context
        if not request:
            return None
        return self.get_image_url(request, size)


class OrderableModelMixin:
    order = graphene.Int()

    @gql_optimizer.resolver_hints(
        model_field='sort_order',
    )
    def resolve_order(self, **kwargs):
        return self.sort_order


class PersonNode(DjangoNode):
    avatar_url = graphene.String(size=graphene.String())

    class Meta:
        model = Person
        only_fields = [
            'id', 'first_name', 'last_name', 'title', 'email', 'organization',
        ]

    def resolve_avatar_url(self, info, size=None):
        request = info.context
        if not request:
            return None
        return self.get_avatar_url(request, size)


class PlanNode(DjangoNode, WithImageMixin):
    id = graphene.ID(source='identifier')
    last_action_identifier = graphene.ID()
    serve_file_base_url = graphene.String()
    pages = graphene.List(pages_schema.Page)
    category_types = graphene.List(
        'aplans.schema.CategoryTypeNode',
        usable_for_indicators=graphene.Boolean(),
        usable_for_actions=graphene.Boolean()
    )
    impact_groups = graphene.List('aplans.schema.ImpactGroupNode', first=graphene.Int())

    static_pages = graphene.List('aplans.schema.StaticPageNode')
    blog_posts = graphene.List('aplans.schema.BlogPostNode')

    main_menu = pages_schema.MenuNode.create_plan_menu_field()

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

    @gql_optimizer.resolver_hints(
        model_field='category_types',
    )
    def resolve_category_types(self, info, usable_for_indicators=None, usable_for_actions=None):
        qs = self.category_types.all()
        if usable_for_indicators is not None:
            qs = qs.filter(usable_for_indicators=usable_for_indicators)
        if usable_for_indicators is not None:
            qs = qs.filter(usable_for_indicators=usable_for_indicators)
        return qs

    @gql_optimizer.resolver_hints(
        model_field='impact_groups',
    )
    def resolve_impact_groups(self, info, first=None):
        qs = self.impact_groups.all()
        if first is not None:
            qs = qs[0:first]
        return qs

    def resolve_pages(self, info):
        if not self.site_id:
            return
        if not self.site.root_page:
            return
        return self.site.root_page.get_descendants(inclusive=True).live().public().type(AplansPage).specific()

    class Meta:
        model = Plan
        only_fields = public_fields(Plan, remove_fields=['image_url'])


class ActionScheduleNode(DjangoNode):
    class Meta:
        model = ActionSchedule
        only_fields = public_fields(ActionSchedule)


class ActionStatusNode(DjangoNode):
    class Meta:
        model = ActionStatus
        only_fields = public_fields(ActionStatus)


class ActionResponsiblePartyNode(DjangoNode):
    class Meta:
        model = ActionResponsibleParty
        only_fields = public_fields(ActionResponsibleParty)


class ActionContactPersonNode(DjangoNode):
    class Meta:
        model = ActionContactPerson
        only_fields = public_fields(ActionContactPerson)


class ActionImpactNode(DjangoNode):
    class Meta:
        model = ActionImpact
        only_fields = public_fields(ActionImpact)


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
        only_fields = public_fields(Category)


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

    @gql_optimizer.resolver_hints(
        model_field='comment',
    )
    def resolve_comment(self, info):
        comment = self.comment
        if comment is None:
            return None

        return RichText(comment)


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
        model_field='description',
    )
    def resolve_description(self, info):
        description = self.description
        if description is None:
            return None

        return RichText(description)

    @gql_optimizer.resolver_hints(
        model_field='categories',
    )
    def resolve_categories(self, info, category_type=None):
        qs = self.categories.all()
        if category_type is not None:
            qs = qs.filter(type__identifier=category_type)
        return qs


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


class Query(indicators_schema.Query):
    plan = gql_optimizer.field(graphene.Field(PlanNode, id=graphene.ID(required=True)))
    all_plans = graphene.List(PlanNode)

    action = graphene.Field(ActionNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())
    person = graphene.Field(PersonNode, id=graphene.ID(required=True))
    static_page = graphene.Field(StaticPageNode, plan=graphene.ID(required=True), slug=graphene.ID(required=True))

    plan_actions = graphene.List(
        ActionNode, plan=graphene.ID(required=True), first=graphene.Int(),
        order_by=graphene.String()
    )
    plan_categories = graphene.List(
        CategoryNode, plan=graphene.ID(required=True), category_type=graphene.ID()
    )
    plan_organizations = graphene.List(
        OrganizationNode, plan=graphene.ID(), with_ancestors=graphene.Boolean(default_value=False)
    )

    def resolve_plan(self, info, **kwargs):
        qs = Plan.objects.all()
        try:
            plan = gql_optimizer.query(qs, info).get(identifier=kwargs['id'])
        except Plan.DoesNotExist:
            return None

        set_active_plan(info, plan)
        return plan

    def resolve_all_plans(self, info):
        return Plan.objects.all()

    def resolve_plan_actions(self, info, plan, first=None, order_by=None, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        qs = Action.objects.filter(plan=plan_obj)
        qs = order_queryset(qs, ActionNode, order_by)
        if first is not None:
            qs = qs[0:first]

        return gql_optimizer.query(qs, info)

    def resolve_categories(self, info, category_type):
        qs = self.categories
        if type is not None:
            qs = qs.filter(type__identifier=type)
        return qs

    def resolve_plan_categories(self, info, plan, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        qs = Category.objects.filter(type__plan=plan_obj)

        category_type = kwargs.get('category_type')
        if category_type is not None:
            qs = qs.filter(type__identifier=category_type)

        return gql_optimizer.query(qs, info)

    def resolve_plan_organizations(self, info, plan, with_ancestors, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        qs = Organization.objects.all()
        if plan is not None:
            qs = qs.filter(responsible_actions__action__plan=plan_obj).distinct()

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
            plan_obj = get_plan_from_context(info, plan)
            if not plan_obj:
                return None
            qs = qs.filter(identifier=identifier, plan=plan_obj)

        qs = gql_optimizer.query(qs, info)

        try:
            obj = qs.get()
        except Action.DoesNotExist:
            return None

        if not identifier:
            set_active_plan(info, obj.plan)

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

    def resolve_static_page(self, info, slug, plan, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if not plan_obj:
            return None

        qs = StaticPage.objects.all()
        qs = qs.filter(slug=slug, plan=plan_obj)
        qs = gql_optimizer.query(qs, info)

        try:
            obj = qs.get()
        except StaticPage.DoesNotExist:
            return None

        return obj


class LocaleDirective(GraphQLDirective):
    def __init__(self):
        super().__init__(
            name='locale',
            description='Select locale in which to return data',
            args={
                'lang': GraphQLArgument(
                    type_=GraphQLNonNull(GraphQLString),
                    description='Selected language'
                )
            },
            locations=[DirectiveLocation.QUERY]
        )


schema = graphene.Schema(
    query=Query,
    directives=specified_directives + [LocaleDirective()],
    types=[] + pages_schema.types
)
