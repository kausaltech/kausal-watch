import graphene
import graphene_django_optimizer as gql_optimizer
import libvoikko
import pytz
from django.db.models import Count, Q
from django_orghierarchy.models import Organization, OrganizationClass
from graphql.error import GraphQLError
from graphql.type import (
    DirectiveLocation, GraphQLArgument, GraphQLDirective, GraphQLNonNull, GraphQLString, specified_directives
)
from grapple.registry import registry as grapple_registry
from grapple.types.pages import PageInterface
from itertools import chain
from wagtail.core.rich_text import RichText

from actions.models import (
    Action, ActionContactPerson, ActionImpact, ActionImplementationPhase, ActionResponsibleParty, ActionSchedule,
    ActionStatus, ActionStatusUpdate, ActionTask, Category, CategoryMetadataChoice, CategoryMetadataRichText,
    CategoryType, ImpactGroup, ImpactGroupAction, MonitoringQualityPoint, Plan, PlanDomain, Scenario
)
from aplans.utils import public_fields
from content.models import SiteGeneralContent
from feedback import schema as feedback_schema
from indicators import schema as indicators_schema
from pages import schema as pages_schema
from pages.models import AplansPage
from people.models import Person

from .graphql_helpers import get_fields
from .graphql_types import DjangoNode, get_plan_from_context, order_queryset, set_active_plan, register_django_node

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


class PlanDomainNode(DjangoNode):
    class Meta:
        model = PlanDomain
        only_fields = [
            'id', 'hostname', 'google_site_verification_tag', 'matomo_analytics_url',
        ]


class PlanNode(DjangoNode):
    id = graphene.ID(source='identifier')
    last_action_identifier = graphene.ID()
    serve_file_base_url = graphene.String()
    primary_language = graphene.String()
    pages = graphene.List(PageInterface)
    category_types = graphene.List(
        'aplans.schema.CategoryTypeNode',
        usable_for_indicators=graphene.Boolean(),
        usable_for_actions=graphene.Boolean()
    )
    impact_groups = graphene.List('aplans.schema.ImpactGroupNode', first=graphene.Int())
    image = graphene.Field('images.schema.ImageNode')

    domain = graphene.Field(PlanDomainNode, hostname=graphene.String(required=False))

    main_menu = pages_schema.MenuNode.create_plan_menu_field()

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

    def resolve_serve_file_base_url(self, info):
        request = info.context
        return request.build_absolute_uri('/').rstrip('/')

    def resolve_pages(self, info):
        if not self.site_id:
            return
        if not self.site.root_page:
            return
        return self.site.root_page.get_descendants(inclusive=True).live().public().type(AplansPage).specific()

    @gql_optimizer.resolver_hints(
        model_field='domains',
    )
    def resolve_domain(self, info, hostname=None):
        if not hostname:
            return None
        return self.domains.filter(hostname=hostname).first()

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


class ActionImplementationPhaseNode(DjangoNode):
    class Meta:
        model = ActionImplementationPhase
        only_fields = public_fields(ActionImplementationPhase)


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


class CategoryMetadataInterface(graphene.Interface):
    id = graphene.ID(required=True)

    @classmethod
    def resolve_type(cls, instance, info):
        if isinstance(instance, CategoryMetadataRichText):
            return CategoryMetadataRichTextNode
        elif isinstance(instance, CategoryMetadataChoice):
            return CategoryMetadataChoiceNode


@register_django_node
class CategoryMetadataChoiceNode(DjangoNode):
    key = graphene.String(required=True)
    key_identifier = graphene.String(required=True)
    value = graphene.String(required=True)
    value_identifier = graphene.String(required=True)

    def resolve_key(self, info):
        return self.metadata.name

    def resolve_key_identifier(self, info):
        return self.metadata.identifier

    def resolve_value(self, info):
        return self.choice.name

    def resolve_value_identifier(self, info):
        return self.choice.identifier

    class Meta:
        model = CategoryMetadataChoice
        interfaces = (CategoryMetadataInterface,)


@register_django_node
class CategoryMetadataRichTextNode(DjangoNode):
    class Meta:
        model = CategoryMetadataRichText
        interfaces = (CategoryMetadataInterface,)


class CategoryTypeNode(DjangoNode):
    class Meta:
        model = CategoryType


@register_django_node
class CategoryNode(DjangoNode):
    image = graphene.Field('images.schema.ImageNode')
    metadata = graphene.List(CategoryMetadataInterface)

    def resolve_metadata(self, info):
        return chain(self.metadata_richtexts.all(), self.metadata_choices.all())

    class Meta:
        model = Category
        only_fields = public_fields(Category)


class ScenarioNode(DjangoNode):
    class Meta:
        model = Scenario
        only_fields = public_fields(Scenario)


class ImpactGroupNode(DjangoNode):
    name = graphene.String()
    image = graphene.Field('images.schema.ImageNode')

    class Meta:
        model = ImpactGroup
        only_fields = public_fields(ImpactGroup, remove_fields=['name'])


class ImpactGroupActionNode(DjangoNode):
    image = graphene.Field('images.schema.ImageNode')

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


@register_django_node
class ActionNode(DjangoNode):
    ORDERABLE_FIELDS = ['updated_at', 'identifier']

    name = graphene.String(hyphenated=graphene.Boolean())
    categories = graphene.List(CategoryNode, category_type=graphene.ID())
    next_action = graphene.Field('aplans.schema.ActionNode')
    previous_action = graphene.Field('aplans.schema.ActionNode')
    image = graphene.Field('images.schema.ImageNode')

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
    action_count = graphene.Int(description='Number of actions this organization is responsible for')
    contact_person_count = graphene.Int(
        description='Number of contact persons that are associated with this organization'
    )

    def resolve_ancestors(self, info):
        return self.get_ancestors()

    @gql_optimizer.resolver_hints(
        only=tuple(),
    )
    def resolve_action_count(self, info):
        return getattr(self, 'action_count', None)

    @gql_optimizer.resolver_hints(
        only=tuple(),
    )
    def resolve_contact_person_count(self, info):
        return getattr(self, 'contact_person_count', None)

    class Meta:
        model = Organization
        only_fields = [
            'id', 'abbreviation', 'parent', 'name', 'classification', 'distinct_name',
        ]


class SiteGeneralContentNode(DjangoNode):
    class Meta:
        model = SiteGeneralContent
        only_fields = public_fields(SiteGeneralContent)


class Query(indicators_schema.Query):
    plan = gql_optimizer.field(graphene.Field(PlanNode, id=graphene.ID(), domain=graphene.String()))
    all_plans = graphene.List(PlanNode)

    action = graphene.Field(ActionNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())
    person = graphene.Field(PersonNode, id=graphene.ID(required=True))

    plan_actions = graphene.List(
        ActionNode, plan=graphene.ID(required=True), first=graphene.Int(),
        category=graphene.ID(), order_by=graphene.String()
    )
    plan_categories = graphene.List(
        CategoryNode, plan=graphene.ID(required=True), category_type=graphene.ID()
    )
    plan_organizations = graphene.List(
        OrganizationNode, plan=graphene.ID(),
        with_ancestors=graphene.Boolean(default_value=False),
        for_responsible_parties=graphene.Boolean(default_value=True),
        for_contact_persons=graphene.Boolean(default_value=False),
    )
    plan_page = graphene.Field(PageInterface, plan=graphene.ID(required=True), path=graphene.String(required=True))

    def resolve_plan(self, info, id=None, domain=None, **kwargs):
        if not id and not domain:
            raise GraphQLError("You must supply either id or domain as arguments to 'plan'", [info])

        qs = Plan.objects.all()
        if id:
            qs = qs.filter(identifier=id.lower())
        if domain:
            qs = qs.for_hostname(domain.lower())

        plan = gql_optimizer.query(qs, info).first()
        if not plan:
            return None

        set_active_plan(info, plan)
        return plan

    def resolve_all_plans(self, info):
        return Plan.objects.all()

    def resolve_plan_actions(self, info, plan, first=None, category=None, order_by=None, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        qs = Action.objects.filter(plan=plan_obj)
        if category is not None:
            qs = qs.filter(categories=category).distinct()

        qs = order_queryset(qs, ActionNode, order_by)
        if first is not None:
            qs = qs[0:first]

        return gql_optimizer.query(qs, info)

    def resolve_plan_page(self, info, plan, path, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        root = plan_obj.root_page
        if not path.endswith('/'):
            path = path + '/'
        qs = root.get_descendants(inclusive=True).live().public().filter(url_path=path).specific()
        return gql_optimizer.query(qs, info).first()

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

    def resolve_plan_organizations(
        self, info, plan, with_ancestors, for_responsible_parties, for_contact_persons,
        **kwargs
    ):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        qs = Organization.objects.all()
        if plan is not None:
            query = Q()
            if for_responsible_parties:
                query |= Q(responsible_actions__action__plan=plan_obj)
            if for_contact_persons:
                query |= Q(people__contact_for_actions__plan=plan_obj)
            qs = qs.filter(query)
        qs = qs.distinct()

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

        selections = get_fields(info)
        if 'actionCount' in selections:
            if plan_obj is not None:
                annotate_filter = Q(responsible_actions__action__plan=plan_obj)
            else:
                annotate_filter = None
            qs = qs.annotate(action_count=Count(
                'responsible_actions__action', distinct=True, filter=annotate_filter
            ))
        if 'contactPersonCount' in selections:
            if plan_obj is not None:
                annotate_filter = Q(people__contact_for_actions__plan=plan_obj)
            else:
                annotate_filter = None
            qs = qs.annotate(contact_person_count=Count(
                'people', distinct=True, filter=annotate_filter
            ))

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


class Mutation(graphene.ObjectType):
    create_user_feedback = feedback_schema.UserFeedbackMutation.Field()


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
    mutation=Mutation,
    directives=specified_directives + [LocaleDirective()],
    types=[] + list(grapple_registry.models.values())
)
