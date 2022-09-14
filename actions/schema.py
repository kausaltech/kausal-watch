from urllib.parse import urlparse
from typing import Optional

import graphene
from graphene_django.converter import convert_django_field_with_choices
import graphene_django_optimizer as gql_optimizer
from django.db.models import Q, Prefetch
from django.forms import ModelForm
from django.utils.translation import get_language
from graphql.error import GraphQLError
from grapple.types.pages import PageInterface
from grapple.registry import registry as grapple_registry
from itertools import chain
from wagtail.core.rich_text import RichText

from actions.action_admin import ActionAdmin
from actions.models import (
    Action, ActionContactPerson, ActionImpact, ActionImplementationPhase, ActionLink, ActionResponsibleParty,
    ActionSchedule, ActionStatus, ActionStatusUpdate, ActionTask, Category, CategoryLevel, AttributeChoice,
    AttributeChoiceWithText, AttributeNumericValue, AttributeRichText, AttributeType, AttributeTypeChoiceOption,
    CategoryType, ImpactGroup, ImpactGroupAction, MonitoringQualityPoint, Plan, PlanDomain, PlanFeatures,
    Scenario, CommonCategory, CommonCategoryType
)
from orgs.models import Organization
from aplans.graphql_helpers import UpdateModelInstanceMutation
from aplans.graphql_types import (
    DjangoNode, GQLInfo, get_plan_from_context, order_queryset, register_django_node, set_active_plan
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
    category_type = graphene.Field('actions.schema.CategoryTypeNode', id=graphene.ID(required=True))
    category_types = graphene.List(
        'actions.schema.CategoryTypeNode',
        usable_for_indicators=graphene.Boolean(),
        usable_for_actions=graphene.Boolean()
    )
    actions = graphene.List(
        'actions.schema.ActionNode', identifier=graphene.ID(), id=graphene.ID(), required=True,
        only_mine=graphene.Boolean(default_value=False), responsible_organization=graphene.ID(required=False)
    )
    action_attribute_types = graphene.List('actions.schema.AttributeTypeNode')
    impact_groups = graphene.List('actions.schema.ImpactGroupNode', first=graphene.Int(), required=True)
    image = graphene.Field('images.schema.ImageNode', required=False)

    primary_orgs = graphene.List('orgs.schema.OrganizationNode', required=True)

    domain = graphene.Field(PlanDomainNode, hostname=graphene.String(required=False))
    domains = graphene.List(PlanDomainNode, hostname=graphene.String(required=False))
    admin_url = graphene.String(required=False)
    view_url = graphene.String(client_url=graphene.String(required=False))

    main_menu = pages_schema.MainMenuNode.create_plan_menu_field()
    footer = pages_schema.FooterNode.create_plan_menu_field()

    # FIXME: Legacy attributes, remove later
    hide_action_identifiers = graphene.Boolean()
    hide_action_official_name = graphene.Boolean()
    hide_action_lead_paragraph = graphene.Boolean()

    features = graphene.Field(PlanFeaturesNode, required=True)
    all_related_plans = graphene.List('actions.schema.PlanNode', required=True)

    def resolve_last_action_identifier(self: Plan, info):
        return self.get_last_action_identifier()

    def resolve_category_type(self, info, id):
        return self.category_types.get(id=id)

    @gql_optimizer.resolver_hints(
        model_field='category_types',
    )
    def resolve_category_types(self: Plan, info, usable_for_indicators=None, usable_for_actions=None):
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

    @gql_optimizer.resolver_hints(
        model_field='domains',
    )
    def resolve_view_url(self: Plan, info, client_url: Optional[str] = None):
        if client_url:
            try:
                urlparse(client_url)
            except Exception:
                raise GraphQLError('clientUrl must be a valid URL', [info])
        return self.get_view_url(client_url=client_url)

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
    def resolve_actions(
        self: Plan, info: GQLInfo, identifier=None, id=None, only_mine=False, responsible_organization=None
    ):
        user = info.context.user
        qs = self.actions.filter(plan=self)
        if identifier:
            qs = qs.filter(identifier=identifier)
        if id:
            qs = qs.filter(id=id)
        if only_mine:
            if not user.is_authenticated or not user.is_staff:
                qs = qs.none()
            else:
                qs = qs.user_has_staff_role_for(user, plan=self)
        if responsible_organization:
            qs = qs.filter(responsible_organizations=responsible_organization)
        return qs

    def resolve_action_attribute_types(self, info):
        return self.action_attribute_types.order_by('pk')

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

    @gql_optimizer.resolver_hints(
        select_related=('parent',),
    )
    def resolve_all_related_plans(self: Plan, info):
        return self.get_all_related_plans()

    @gql_optimizer.resolver_hints(
        select_related=('image',),
        only=('image',)
    )
    def resolve_image(root: Plan, info):
        return root.image

    class Meta:
        model = Plan
        fields = public_fields(Plan)


class AttributeInterface(graphene.Interface):
    id = graphene.ID(required=True)
    key = graphene.String(required=True)
    key_identifier = graphene.String(required=True)

    def resolve_key(self, info):
        return self.type.name

    def resolve_key_identifier(self, info):
        return self.type.identifier

    @classmethod
    def resolve_type(cls, instance, info):
        if isinstance(instance, AttributeRichText):
            return AttributeRichTextNode
        elif isinstance(instance, AttributeChoice):
            return AttributeChoiceNode
        elif isinstance(instance, AttributeChoiceWithText):
            return AttributeChoiceWithTextNode
        elif isinstance(instance, AttributeNumericValue):
            return AttributeNumericValueNode


@register_django_node
class AttributeChoiceWithTextNode(DjangoNode):
    choice = graphene.String(required=False)
    choice_identifier = graphene.String(required=False)
    text = graphene.String(required=False)

    def resolve_choice(self, info):
        return self.choice.name

    def resolve_choice_identifier(self, info):
        return self.choice.identifier

    def resolve_text(self, info):
        return self.text

    class Meta:
        model = AttributeChoiceWithText
        interfaces = (AttributeInterface,)


@register_django_node
class AttributeChoiceNode(DjangoNode):
    value = graphene.String(required=True)
    value_identifier = graphene.String(required=True)

    def resolve_value(self, info):
        return self.choice.name

    def resolve_value_identifier(self, info):
        return self.choice.identifier

    class Meta:
        model = AttributeChoice
        interfaces = (AttributeInterface,)


@register_django_node
class AttributeRichTextNode(DjangoNode):
    value = graphene.String(required=True)

    def resolve_value(self, info):
        return self.text

    class Meta:
        model = AttributeRichText
        interfaces = (AttributeInterface,)
        # We expose `value` instead of `text`
        fields = public_fields(AttributeRichText, remove_fields=['text'])


@register_django_node
class AttributeNumericValueNode(DjangoNode):
    class Meta:
        model = AttributeNumericValue
        interfaces = (AttributeInterface,)
        fields = public_fields(AttributeNumericValue)


class CategoryLevelNode(DjangoNode):
    class Meta:
        model = CategoryLevel
        fields = public_fields(CategoryLevel)


@register_django_node
class AttributeTypeNode(DjangoNode):
    class Meta:
        model = AttributeType
        fields = public_fields(AttributeType)


@register_django_node
class AttributeTypeChoiceOptionNode(DjangoNode):
    class Meta:
        model = AttributeTypeChoiceOption
        fields = public_fields(AttributeTypeChoiceOption)


# TODO: Remove this when production UI is updated
class ResolveShortDescriptionFromLeadParagraphShim:
    short_description = graphene.String()

    def resolve_short_description(root, info):
        return root.lead_paragraph


@register_django_node
class CategoryTypeNode(ResolveShortDescriptionFromLeadParagraphShim, DjangoNode):
    attribute_types = graphene.List(AttributeTypeNode)
    selection_type = convert_django_field_with_choices(CategoryType._meta.get_field('select_widget'))
    categories = graphene.List(
        'actions.schema.CategoryNode', only_root=graphene.Boolean(default_value=False)
    )

    class Meta:
        model = CategoryType
        fields = public_fields(CategoryType, remove_fields=['select_widget'])

    def resolve_attribute_types(self, info):
        return self.attribute_types.order_by('pk')

    @gql_optimizer.resolver_hints(
        model_field='select_widget',
    )
    def resolve_selection_type(self: CategoryType, info):
        return self.select_widget

    @gql_optimizer.resolver_hints(
        model_field='categories',
    )
    def resolve_categories(self: CategoryType, info, only_root: bool):
        qs = self.categories.all()
        if only_root:
            qs = qs.filter(parent__isnull=True)
        return qs


@register_django_node
class CommonCategoryTypeNode(ResolveShortDescriptionFromLeadParagraphShim, DjangoNode):
    class Meta:
        model = CommonCategoryType
        fields = public_fields(CommonCategoryType)


def get_translated_category_page(info, **kwargs):
    qs = CategoryPage.objects.filter(locale__language_code__iexact=get_language())
    return Prefetch('category_pages', to_attr='category_pages_locale', queryset=qs)


class AttributesMixin:
    attributes = graphene.List(AttributeInterface, id=graphene.ID(required=False))

    def resolve_attributes(self, info, id=None):
        query = Q()
        if id is not None:
            query = Q(type__identifier=id)
        attributes = chain(
            self.rich_text_attributes.filter(query),
            self.choice_attributes.filter(query),
            self.choice_with_text_attributes.filter(query),
            self.numeric_value_attributes.filter(query)
        )
        return sorted(attributes, key=lambda a: a.type.order)


@register_django_node
class CategoryNode(ResolveShortDescriptionFromLeadParagraphShim, AttributesMixin, DjangoNode):
    image = graphene.Field('images.schema.ImageNode')
    attributes = graphene.List(AttributeInterface, id=graphene.ID(required=False))
    level = graphene.Field(CategoryLevelNode)
    actions = graphene.List('actions.schema.ActionNode')
    icon_image = graphene.Field('images.schema.ImageNode')
    icon_svg_url = graphene.String()
    category_page = graphene.Field(grapple_registry.pages[CategoryPage])

    def resolve_image(self, info):
        if self.image:
            return self.image
        if self.common:
            return self.common.image
        return None

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

    @gql_optimizer.resolver_hints(
        prefetch_related=get_translated_category_page
    )
    def resolve_category_page(self, info):
        # If we have prefetched the page in the right locale, use that
        if hasattr(self, 'category_pages_locale'):
            pages = self.category_pages_locale
            if not len(pages):
                return None
            return pages[0]

        try:
            return self.category_pages.get(locale__language_code__iexact=get_language())
        except CategoryPage.DoesNotExist:
            return None

    @gql_optimizer.resolver_hints(
        prefetch_related=('icons',),
        select_related=('common',),
        only=('common',)
    )
    def resolve_icon_image(root: Category, info):
        icon = root.get_icon(get_language())
        if icon:
            return icon.image
        return None

    @gql_optimizer.resolver_hints(
        prefetch_related=('icons',),
        select_related=('common',),
        only=('common',)
    )
    def resolve_icon_svg_url(root: Category, info):
        icon = root.get_icon(get_language())
        if icon and icon.svg:
            return info.context.build_absolute_uri(icon.svg.file.url)
        return None

    class Meta:
        model = Category
        fields = public_fields(Category, add_fields=['level', 'icon_image', 'icon_svg_url'])


@register_django_node
class CommonCategoryNode(ResolveShortDescriptionFromLeadParagraphShim, DjangoNode):
    icon_image = graphene.Field('images.schema.ImageNode')
    icon_svg_url = graphene.String()

    def resolve_icon_image(root, info):
        icon = root.get_icon(get_language())
        if icon:
            return icon.image
        return None

    def resolve_icon_svg_url(root, info):
        icon = root.get_icon(get_language())
        if icon and icon.svg:
            return info.context.build_absolute_uri(icon.svg.file.url)
        return None

    class Meta:
        model = CommonCategory
        fields = public_fields(CommonCategory)


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
class ActionNode(AttributesMixin, DjangoNode):
    ORDERABLE_FIELDS = ['updated_at', 'identifier']

    name = graphene.String(hyphenated=graphene.Boolean())
    categories = graphene.List(CategoryNode, category_type=graphene.ID())
    contact_persons = graphene.List('actions.schema.ActionContactPersonNode')
    next_action = graphene.Field('actions.schema.ActionNode')
    previous_action = graphene.Field('actions.schema.ActionNode')
    image = graphene.Field('images.schema.ImageNode')
    view_url = graphene.String(client_url=graphene.String(required=False))
    edit_url = graphene.String()
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
        select_related=('plan'),
        only=('name', 'i18n', 'plan__primary_language'),
    )
    def resolve_name(self, info, hyphenated=False):
        name = self.name_i18n
        if name is None:
            return None
        if hyphenated:
            name = hyphenate(name)
        return name

    @gql_optimizer.resolver_hints(
        model_field=('description', 'i18n'),
    )
    def resolve_description(self: Action, info):
        description = self.description_i18n
        if description is None:
            return None
        return RichText(description)

    @gql_optimizer.resolver_hints(
        model_field=('plan', 'identifier')
    )
    def resolve_view_url(self: Action, info, client_url: Optional[str] = None):
        return self.get_view_url(client_url=client_url)

    def resolve_edit_url(self: Action, info):
        client_plan = self.plan.clients.first()
        if client_plan is None:
            return None
        base_url = client_plan.client.get_admin_url().rstrip('/')
        url_helper = ActionAdmin().url_helper
        edit_url = url_helper.get_action_url('edit', self.id).lstrip('/')
        return f'{base_url}/{edit_url}'

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
    my_plans = graphene.List(PlanNode)

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

    def resolve_my_plans(self, info: GQLInfo):
        user = info.context.user
        if user is None:
            return []
        plans = Plan.objects.user_has_staff_role_for(info.context.user)
        return gql_optimizer.query(plans, info)

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
