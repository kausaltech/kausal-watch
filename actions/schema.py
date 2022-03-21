import graphene
import graphene_django_optimizer as gql_optimizer
from django.db.models.query_utils import Q
from django.forms import ModelForm
from django.urls.base import reverse
from django.utils.translation import get_language
from graphql.error import GraphQLError
from grapple.types.pages import PageInterface
from grapple.registry import registry as grapple_registry
from itertools import chain
from wagtail.core.rich_text import RichText

from actions.models import (
    Action, ActionContactPerson, ActionImpact, ActionImplementationPhase, ActionLink, ActionResponsibleParty,
    ActionSchedule, ActionStatus, ActionStatusUpdate, ActionTask, Category, CategoryLevel, CategoryMetadataChoice,
    CategoryMetadataNumericValue, CategoryMetadataRichText, CategoryType, CategoryTypeMetadata,
    CategoryTypeMetadataChoice, ImpactGroup, ImpactGroupAction, MonitoringQualityPoint, Plan, PlanDomain, Scenario,
    PlanFeatures
)
from orgs.models import Organization
from aplans.graphql_helpers import UpdateModelInstanceMutation
from aplans.graphql_types import (
    DjangoNode, get_plan_from_context, order_queryset, register_django_node, set_active_plan
)
from aplans.utils import hyphenate, public_fields
from pages import schema as pages_schema
from pages.models import AplansPage, CategoryPage
from search.backends import get_search_backend


class PlanDomainNode(DjangoNode):
    class Meta:
        model = PlanDomain
        fields = [
            'id', 'hostname', 'base_path', 'google_site_verification_tag', 'matomo_analytics_url',
        ]


class PlanFeaturesNode(DjangoNode):
    class Meta:
        model = PlanFeatures
        fields = public_fields(PlanFeatures)


class PlanNode(DjangoNode):
    id = graphene.ID(source='identifier', required=True)
    last_action_identifier = graphene.ID()
    serve_file_base_url = graphene.String(required=True)
    primary_language = graphene.String(required=True)
    pages = graphene.List(PageInterface)
    category_types = graphene.List(
        'actions.schema.CategoryTypeNode',
        usable_for_indicators=graphene.Boolean(),
        usable_for_actions=graphene.Boolean()
    )
    actions = graphene.List('actions.schema.ActionNode', identifier=graphene.ID(), id=graphene.ID(), required=True)
    impact_groups = graphene.List('actions.schema.ImpactGroupNode', first=graphene.Int(), required=True)
    image = graphene.Field('images.schema.ImageNode', required=False)

    primary_orgs = graphene.List('orgs.schema.OrganizationNode', required=True)

    domain = graphene.Field(PlanDomainNode, hostname=graphene.String(required=False))
    domains = graphene.List(PlanDomainNode, hostname=graphene.String(required=False))
    admin_url = graphene.String(required=False)

    main_menu = pages_schema.MainMenuNode.create_plan_menu_field()
    footer = pages_schema.FooterNode.create_plan_menu_field()

    # FIXME: Legacy attributes, remove later
    hide_action_identifiers = graphene.Boolean()
    hide_action_official_name = graphene.Boolean()
    hide_action_lead_paragraph = graphene.Boolean()

    features = graphene.Field(PlanFeaturesNode, required=True)

    def resolve_last_action_identifier(self, info):
        return self.get_last_action_identifier()

    @gql_optimizer.resolver_hints(
        model_field='category_types',
    )
    def resolve_category_types(self, info, usable_for_indicators=None, usable_for_actions=None):
        qs = self.category_types.all()
        if usable_for_indicators is not None:
            qs = qs.filter(usable_for_indicators=usable_for_indicators)
        if usable_for_indicators is not None:
            qs = qs.filter(usable_for_indicators=usable_for_indicators)
        return qs.order_by('pk')

    @gql_optimizer.resolver_hints(
        model_field='impact_groups',
    )
    def resolve_impact_groups(self, info, first=None):
        qs = self.impact_groups.all()
        if first is not None:
            qs = qs[0:first]
        return qs.order_by('pk')

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
        context_hostname = getattr(info.context, '_plan_hostname', None)
        if not hostname:
            hostname = context_hostname
            if not hostname:
                return None
        return self.domains.filter(plan=self, hostname=hostname).first()

    @gql_optimizer.resolver_hints(
        model_field='domains',
    )
    def resolve_domains(self, info, hostname=None):
        context_hostname = getattr(info.context, '_plan_hostname', None)
        if not hostname:
            hostname = context_hostname
            if not hostname:
                return None
        return self.domains.filter(plan=self, hostname=hostname)

    def resolve_admin_url(self: Plan, info):
        if not self.features.show_admin_link:
            return None
        client_plan = self.clients.first()
        if client_plan is None:
            return None
        return client_plan.client.get_admin_url()

    @gql_optimizer.resolver_hints(
        model_field='actions',
    )
    def resolve_actions(self, info, identifier=None, id=None):
        qs = self.actions.filter(plan=self)
        if identifier:
            qs = qs.filter(identifier=identifier)
        if id:
            qs = qs.filter(id=id)
        return qs

    def resolve_primary_orgs(self, info):
        qs = self.actions.all().values('primary_org')
        return Organization.objects.filter(id__in=qs)

    @gql_optimizer.resolver_hints(
        select_related=('features',)
    )
    def resolve_hide_action_identifiers(self: Plan, info):
        return not self.features.has_action_identifiers

    @gql_optimizer.resolver_hints(
        select_related=('features',)
    )
    def resolve_hide_action_lead_paragraph(self: Plan, info):
        return not self.features.has_action_lead_paragraph

    @gql_optimizer.resolver_hints(
        select_related=('features',)
    )
    def resolve_hide_action_official_name(self: Plan, info):
        return not self.features.has_action_official_name

    class Meta:
        model = Plan
        fields = public_fields(Plan)


class CategoryMetadataInterface(graphene.Interface):
    id = graphene.ID(required=True)
    key = graphene.String(required=True)
    key_identifier = graphene.String(required=True)

    def resolve_key(self, info):
        return self.metadata.name

    def resolve_key_identifier(self, info):
        return self.metadata.identifier

    @classmethod
    def resolve_type(cls, instance, info):
        if isinstance(instance, CategoryMetadataRichText):
            return CategoryMetadataRichTextNode
        elif isinstance(instance, CategoryMetadataChoice):
            return CategoryMetadataChoiceNode
        elif isinstance(instance, CategoryMetadataNumericValue):
            return CategoryMetadataNumericValueNode


@register_django_node
class CategoryMetadataChoiceNode(DjangoNode):
    value = graphene.String(required=True)
    value_identifier = graphene.String(required=True)

    def resolve_value(self, info):
        return self.choice.name

    def resolve_value_identifier(self, info):
        return self.choice.identifier

    class Meta:
        model = CategoryMetadataChoice
        interfaces = (CategoryMetadataInterface,)


@register_django_node
class CategoryMetadataRichTextNode(DjangoNode):
    value = graphene.String(required=True)

    def resolve_value(self, info):
        return self.text

    class Meta:
        model = CategoryMetadataRichText
        interfaces = (CategoryMetadataInterface,)
        # We expose `value` instead of `text`
        fields = public_fields(CategoryMetadataRichText, remove_fields=['text'])


@register_django_node
class CategoryMetadataNumericValueNode(DjangoNode):
    class Meta:
        model = CategoryMetadataNumericValue
        interfaces = (CategoryMetadataInterface,)
        fields = public_fields(CategoryMetadataNumericValue)


class CategoryLevelNode(DjangoNode):
    class Meta:
        model = CategoryLevel
        fields = public_fields(CategoryLevel)


@register_django_node
class CategoryTypeMetadataNode(DjangoNode):
    class Meta:
        model = CategoryTypeMetadata
        fields = public_fields(CategoryTypeMetadata)


@register_django_node
class CategoryTypeMetadataChoiceNode(DjangoNode):
    class Meta:
        model = CategoryTypeMetadataChoice
        fields = public_fields(CategoryTypeMetadataChoice)


@register_django_node
class CategoryTypeNode(DjangoNode):
    metadata = graphene.List(CategoryTypeMetadataNode)

    class Meta:
        model = CategoryType
        fields = public_fields(CategoryType)

    def resolve_metadata(self, info):
        return self.metadata.order_by('pk')


@register_django_node
class CategoryNode(DjangoNode):
    image = graphene.Field('images.schema.ImageNode')
    metadata = graphene.List(CategoryMetadataInterface, id=graphene.ID(required=False))
    level = graphene.Field(CategoryLevelNode)
    actions = graphene.List('actions.schema.ActionNode')
    icon_url = graphene.String()
    category_page = graphene.Field(grapple_registry.pages[CategoryPage])

    def resolve_metadata(self, info, id=None):
        query = Q()
        if id is not None:
            query = Q(metadata__identifier=id)
        metadata = chain(
            self.metadata_richtexts.filter(query),
            self.metadata_choices.filter(query),
            self.metadata_numeric_values.filter(query)
        )
        return sorted(metadata, key=lambda m: m.metadata.order)

    def resolve_level(self, info):
        depth = 0
        obj = self
        # Uh oh, Category is not a tree model yet
        while obj.parent is not None:
            obj = obj.parent
            depth += 1
            if depth == 5:
                break

        levels = list(self.type.levels.all())
        if depth >= len(levels):
            return None
        return levels[depth]

    def resolve_actions(self, info):
        return self.action_set.all()

    def resolve_icon_url(self, info):
        if not hasattr(self, 'icon'):
            return None
        request = info.context
        path = reverse('category-icon', kwargs=dict(id=self.icon.id)) + '?%s' % int(self.icon.updated_at.timestamp())
        uri = request.build_absolute_uri(path)
        return uri

    def resolve_category_page(self, info):
        try:
            return self.category_pages.get(locale__language_code=get_language())
        except CategoryPage.DoesNotExist:
            return None

    class Meta:
        model = Category
        fields = public_fields(Category, add_fields=['level', 'icon_url'])


class ScenarioNode(DjangoNode):
    class Meta:
        model = Scenario
        fields = public_fields(Scenario)


class ImpactGroupNode(DjangoNode):
    class Meta:
        model = ImpactGroup
        fields = public_fields(ImpactGroup)


class ImpactGroupActionNode(DjangoNode):
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
        self.i18n  # Workaround to avoid i18n field being deferred in gql_optimizer
        comment = self.comment_i18n
        if comment is None:
            return None

        return RichText(comment)


@register_django_node
class ActionNode(DjangoNode):
    ORDERABLE_FIELDS = ['updated_at', 'identifier']

    name = graphene.String(hyphenated=graphene.Boolean())
    categories = graphene.List(CategoryNode, category_type=graphene.ID())
    contact_persons = graphene.List('actions.schema.ActionContactPersonNode')
    next_action = graphene.Field('actions.schema.ActionNode')
    previous_action = graphene.Field('actions.schema.ActionNode')
    image = graphene.Field('images.schema.ImageNode')
    similar_actions = graphene.List('actions.schema.ActionNode')

    class Meta:
        model = Action
        fields = Action.public_fields

    def resolve_next_action(self, info):
        return self.get_next_action()

    def resolve_previous_action(self, info):
        return self.get_previous_action()

    @gql_optimizer.resolver_hints(
        model_field='name',
    )
    def resolve_name(self, info, hyphenated=False):
        self.i18n  # Workaround to avoid i18n field being deferred in gql_optimizer
        name = self.name_i18n
        if name is None:
            return None
        if hyphenated:
            name = hyphenate(name)
        return name

    @gql_optimizer.resolver_hints(
        model_field='description',
    )
    def resolve_description(self, info):
        self.i18n  # Workaround to avoid i18n field being deferred in gql_optimizer
        description = self.description_i18n
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

    @gql_optimizer.resolver_hints(
        model_field='contact_persons',
    )
    def resolve_contact_persons(self, info):
        plan: Plan = get_plan_from_context(info)
        if not plan.features.public_contact_persons:
            return []
        return self.contact_persons.all()

    def resolve_similar_actions(self: Action, info):
        backend = get_search_backend()
        if backend is None:
            return []
        backend.more_like_this(self)
        return []


class ActionScheduleNode(DjangoNode):
    class Meta:
        model = ActionSchedule
        fields = public_fields(ActionSchedule)


class ActionStatusNode(DjangoNode):
    class Meta:
        model = ActionStatus
        fields = public_fields(ActionStatus)


class ActionImplementationPhaseNode(DjangoNode):
    class Meta:
        model = ActionImplementationPhase
        fields = public_fields(ActionImplementationPhase)


class ActionResponsiblePartyNode(DjangoNode):
    class Meta:
        model = ActionResponsibleParty
        fields = public_fields(ActionResponsibleParty)


class ActionContactPersonNode(DjangoNode):
    class Meta:
        model = ActionContactPerson
        fields = public_fields(ActionContactPerson)


class ActionImpactNode(DjangoNode):
    class Meta:
        model = ActionImpact
        fields = public_fields(ActionImpact)


class ActionStatusUpdateNode(DjangoNode):
    class Meta:
        model = ActionStatusUpdate
        fields = [
            'id', 'action', 'title', 'date', 'author', 'content'
        ]


class ActionLinkNode(DjangoNode):
    class Meta:
        model = ActionLink
        fields = public_fields(ActionLink)


class Query:
    plan = gql_optimizer.field(graphene.Field(PlanNode, id=graphene.ID(), domain=graphene.String()))
    plans_for_hostname = graphene.List(PlanNode, hostname=graphene.String())

    action = graphene.Field(ActionNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())

    plan_actions = graphene.List(
        ActionNode, plan=graphene.ID(required=True), first=graphene.Int(),
        category=graphene.ID(), order_by=graphene.String()
    )
    plan_categories = graphene.List(
        CategoryNode, plan=graphene.ID(required=True), category_type=graphene.ID()
    )

    category = graphene.Field(
        CategoryNode, plan=graphene.ID(required=True), category_type=graphene.ID(required=True),
        external_identifier=graphene.ID(required=True)
    )

    def resolve_plan(self, info, id=None, domain=None, **kwargs):
        if not id and not domain:
            raise GraphQLError("You must supply either id or domain as arguments to 'plan'", [info])

        qs = Plan.objects.all()
        if id:
            qs = qs.filter(identifier=id.lower())
        if domain:
            qs = qs.for_hostname(domain.lower())
            info.context._plan_hostname = domain

        plan = gql_optimizer.query(qs, info).first()
        if not plan:
            return None

        set_active_plan(info, plan)
        return plan

    def resolve_plans_for_hostname(self, info, hostname: str):
        info.context._plan_hostname = hostname
        plans = Plan.objects.for_hostname(hostname.lower())
        return list(gql_optimizer.query(plans, info))

    def resolve_plan_actions(self, info, plan, first=None, category=None, order_by=None, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        qs = Action.objects.filter(plan=plan_obj)
        if category is not None:
            # FIXME: This is sucky, maybe convert Category to a proper tree model?
            f = Q(id=category) | Q(parent=category) | Q(parent__parent=category) | Q(parent__parent__parent=category) | Q(parent__parent__parent__parent=category)
            descendant_cats = Category.objects.filter(f)
            qs = qs.filter(categories__in=descendant_cats).distinct()

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

    def resolve_category(self, info, plan, category_type, external_identifier):
        plan_obj = get_plan_from_context(info, plan)
        if not plan_obj:
            return None
        return Category.objects.get(
            type__plan=plan_obj, type__identifier=category_type, external_identifier=external_identifier
        )


class ActionResponsiblePartyForm(ModelForm):
    # TODO: Eventually we will want to allow updating things other than organization
    class Meta:
        model = ActionResponsibleParty
        fields = ['organization']


class UpdateActionResponsiblePartyMutation(UpdateModelInstanceMutation):
    class Meta:
        form_class = ActionResponsiblePartyForm


class PlanForm(ModelForm):
    # TODO: Eventually we will want to allow updating things other than organization
    class Meta:
        model = Plan
        fields = ['organization']


class UpdatePlanMutation(UpdateModelInstanceMutation):
    class Meta:
        form_class = PlanForm


class Mutation(graphene.ObjectType):
    update_plan = UpdatePlanMutation.Field()
    update_action_responsible_party = UpdateActionResponsiblePartyMutation.Field()
