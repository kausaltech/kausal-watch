import graphene
import graphene_django_optimizer as gql_optimizer
from aplans.graphql_types import (
    DjangoNode, get_plan_from_context, order_queryset, register_django_node, set_active_plan
)
from aplans.utils import hyphenate, public_fields
from django.urls import reverse
from graphql.error import GraphQLError
from grapple.types.pages import PageInterface
from itertools import chain
from wagtail.core.rich_text import RichText

from actions.models import (
    Action, ActionContactPerson, ActionImpact, ActionImplementationPhase, ActionResponsibleParty, ActionSchedule,
    ActionStatus, ActionStatusUpdate, ActionTask, Category, CategoryLevel, CategoryMetadataChoice,
    CategoryMetadataRichText, CategoryType, CategoryTypeMetadata, CategoryTypeMetadataChoice, ImpactGroup,
    ImpactGroupAction, MonitoringQualityPoint, Plan, PlanDomain, Scenario
)
from pages import schema as pages_schema
from pages.models import AplansPage


class PlanDomainNode(DjangoNode):
    class Meta:
        model = PlanDomain
        fields = [
            'id', 'hostname', 'google_site_verification_tag', 'matomo_analytics_url',
        ]


class PlanNode(DjangoNode):
    id = graphene.ID(source='identifier')
    last_action_identifier = graphene.ID()
    serve_file_base_url = graphene.String()
    primary_language = graphene.String()
    pages = graphene.List(PageInterface)
    category_types = graphene.List(
        'actions.schema.CategoryTypeNode',
        usable_for_indicators=graphene.Boolean(),
        usable_for_actions=graphene.Boolean()
    )
    actions = graphene.List('actions.schema.ActionNode', identifier=graphene.ID(), id=graphene.ID())
    impact_groups = graphene.List('actions.schema.ImpactGroupNode', first=graphene.Int())
    image = graphene.Field('images.schema.ImageNode')

    domain = graphene.Field(PlanDomainNode, hostname=graphene.String(required=False))
    admin_url = graphene.String(required=False)

    main_menu = pages_schema.MainMenuNode.create_plan_menu_field()
    footer = pages_schema.FooterNode.create_plan_menu_field()

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

    def resolve_admin_url(self, info):
        if not self.show_admin_link:
            return None
        return info.context.build_absolute_uri(reverse('wagtailadmin_home'))

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

    class Meta:
        model = Plan
        fields = public_fields(Plan, remove_fields=['image_url'])


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
    key = graphene.String(required=True)
    key_identifier = graphene.String(required=True)
    value = graphene.String(required=True)

    def resolve_key(self, info):
        return self.metadata.name

    def resolve_key_identifier(self, info):
        return self.metadata.identifier

    def resolve_value(self, info):
        return self.text

    class Meta:
        model = CategoryMetadataRichText
        interfaces = (CategoryMetadataInterface,)
        # We expose `value` instead of `text`
        fields = public_fields(CategoryMetadataRichText, remove_fields=['text'])


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
    class Meta:
        model = CategoryType
        fields = public_fields(CategoryType)


@register_django_node
class CategoryNode(DjangoNode):
    image = graphene.Field('images.schema.ImageNode')
    metadata = graphene.List(CategoryMetadataInterface)
    level = graphene.Field(CategoryLevelNode)

    def resolve_metadata(self, info):
        metadata = chain(self.metadata_richtexts.all(), self.metadata_choices.all())
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

    class Meta:
        model = Category
        fields = public_fields(Category, add_fields=['level'])


class ScenarioNode(DjangoNode):
    class Meta:
        model = Scenario
        fields = public_fields(Scenario)


class ImpactGroupNode(DjangoNode):
    name = graphene.String()
    image = graphene.Field('images.schema.ImageNode')

    class Meta:
        model = ImpactGroup
        fields = public_fields(ImpactGroup, remove_fields=['name'])


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
    next_action = graphene.Field('actions.schema.ActionNode')
    previous_action = graphene.Field('actions.schema.ActionNode')
    image = graphene.Field('images.schema.ImageNode')

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


class Query:
    plan = gql_optimizer.field(graphene.Field(PlanNode, id=graphene.ID(), domain=graphene.String()))
    all_plans = graphene.List(PlanNode)

    action = graphene.Field(ActionNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())

    plan_actions = graphene.List(
        ActionNode, plan=graphene.ID(required=True), first=graphene.Int(),
        category=graphene.ID(), order_by=graphene.String()
    )
    plan_categories = graphene.List(
        CategoryNode, plan=graphene.ID(required=True), category_type=graphene.ID()
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
