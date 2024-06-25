from __future__ import annotations

import graphene
import graphene_django_optimizer as gql_optimizer
import logging
import sentry_sdk
import typing
import uuid
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q, Prefetch, prefetch_related_objects
from django.forms import ModelForm
from django.utils.translation import get_language
from graphene_django import DjangoObjectType
from graphene_django.converter import convert_django_field_with_choices
from graphql.error import GraphQLError
from grapple.registry import registry as grapple_registry
from grapple.types.pages import PageInterface
from itertools import chain
from typing import Generic, Iterable, Optional, Protocol, TypeVar
from urllib.parse import urlparse
from wagtail.models import Revision, WorkflowState
from wagtail.rich_text import RichText


from actions.action_admin import ActionAdmin
from actions.models import (
    Action, ActionContactPerson, ActionImpact,
    ActionImplementationPhase, ActionLink, ActionResponsibleParty,
    ActionSchedule, ActionStatus, ActionStatusUpdate, ActionTask,
    Category, CategoryLevel, AttributeCategoryChoice, AttributeChoice as AttributeChoiceModel,
    AttributeChoiceWithText, AttributeNumericValue, AttributeText, AttributeRichText,
    AttributeType, AttributeTypeChoiceOption, CategoryType,
    ImpactGroup, ImpactGroupAction, MonitoringQualityPoint, Plan,
    PlanDomain, PublicationStatus, PlanFeatures, Scenario, CommonCategory,
    CommonCategoryType
)
from actions.action_status_summary import (
    ActionStatusSummaryIdentifier, ActionTimelinessIdentifier, Sentiment as SentimentEnum, Comparison
)
from actions.models.action import ActionQuerySet
from actions.models.action_deps import ActionDependencyRelationship, ActionDependencyRole
from actions.models.attributes import ModelWithAttributes
from budget.models import Dataset, DatasetScope
from orgs.models import Organization
from people.models import Person
from users.models import User
from aplans.graphql_helpers import AdminButtonsMixin, UpdateModelInstanceMutation
from aplans.graphql_types import (
    DjangoNode,
    GQLInfo,
    WorkflowStateEnum,
    WorkflowStateDescription,
    get_plan_from_context,
    order_queryset,
    register_django_node,
    register_graphene_node,
    set_active_plan
)
from aplans.cache import SerializedDictWithRelatedObjectCache
from aplans.types import is_authenticated
from aplans.utils import hyphenate_fi, public_fields
from pages import schema as pages_schema
from pages.models import AplansPage, CategoryPage, Page, ActionListPage
from search.backends import get_search_backend

if typing.TYPE_CHECKING:
    from actions.models.attributes import Attribute
    from aplans.cache import PlanSpecificCache


logger = logging.getLogger(__name__)
PublicationStatusNode = graphene.Enum.from_enum(PublicationStatus)


class PlanDomainNode(DjangoNode):
    status = PublicationStatusNode(source='status')
    status_message = graphene.String(required=False, source='status_message')

    class Meta:
        model = PlanDomain
        fields = (
            'id',
            'hostname',
            'base_path',
            'google_site_verification_tag',
            'matomo_analytics_url',
            'status',
            'status_message'
        )


class PlanFeaturesNode(DjangoNode):
    public_contact_persons = graphene.Boolean(required=True)
    enable_moderation_workflow = graphene.Boolean()

    class Meta:
        model = PlanFeatures
        fields = public_fields(PlanFeatures)

    @staticmethod
    def resolve_public_contact_persons(root: PlanFeatures, info: GQLInfo) -> bool:
        return root.public_contact_persons

    @staticmethod
    def resolve_enable_moderation_workflow(root: PlanFeatures, info: GQLInfo) -> bool:
        return root.enable_moderation_workflow


def get_action_list_page_node():
    from grapple.registry import registry
    from pages.models import ActionListPage

    return registry.pages[ActionListPage]


T = TypeVar('T', bound=Plan)


class PlanInterface(graphene.Interface, Generic[T]):
    primary_language = graphene.String(required=True)
    published_at = graphene.DateTime()
    domain = graphene.Field(PlanDomainNode, hostname=graphene.String(required=False))
    domains = graphene.List(PlanDomainNode, hostname=graphene.String(required=False))

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='domains',
    )
    def resolve_domain(root: Plan, info, hostname=None):
        context_hostname = getattr(info.context, '_plan_hostname', None)
        if not hostname:
            hostname = context_hostname
            if not hostname:
                return None
        return root.domains.filter(plan=root, hostname=hostname).first()

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='domains',
    )
    def resolve_domains(root: Plan, info, hostname=None):
        context_hostname = getattr(info.context, '_plan_hostname', None)
        if not hostname:
            hostname = context_hostname
            if not hostname:
                return None
        return root.domains.filter(plan=root, hostname=hostname)

    @classmethod
    def resolve_type(cls, instance, info):
        context_hostname = getattr(info.context, '_plan_hostname', None)
        if context_hostname is None:
            return RestrictedPlanNode
        domain = instance.domains.filter(plan=instance, hostname=context_hostname)
        # Having no domains means that this domain match is for a non-production site,
        # hence the full plan schema must be used.
        if not domain or domain.first().status == PublicationStatus.PUBLISHED:
            return PlanNode
        return RestrictedPlanNode


@register_graphene_node
class RestrictedPlanNode(DjangoObjectType):
    class Meta:
        interfaces = (PlanInterface,)
        model = Plan
        fields = ('primary_language', 'published_at', 'domain', 'domains')


class PlanNode(DjangoNode):
    id = graphene.ID(source='identifier', required=True)
    last_action_identifier = graphene.ID()
    serve_file_base_url = graphene.String(required=True)
    pages = graphene.List(PageInterface)
    action_list_page = graphene.Field(get_action_list_page_node)
    category_type = graphene.Field('actions.schema.CategoryTypeNode', id=graphene.ID(required=True))
    category_types = graphene.List(
        graphene.NonNull('actions.schema.CategoryTypeNode'),
        required=True,
        usable_for_indicators=graphene.Boolean(),
        usable_for_actions=graphene.Boolean()
    )
    actions = graphene.List(
        graphene.NonNull('actions.schema.ActionNode'), identifier=graphene.ID(), id=graphene.ID(),
        only_mine=graphene.Boolean(default_value=False), responsible_organization=graphene.ID(required=False),
        first=graphene.Int(required=False), restrict_to_publicly_visible=graphene.Boolean(default_value=True), required=True,
    )
    action_attribute_types = graphene.List(
        graphene.NonNull('actions.schema.AttributeTypeNode', required=True), required=True
    )
    impact_groups = graphene.List('actions.schema.ImpactGroupNode', first=graphene.Int(), required=True)
    image = graphene.Field('images.schema.ImageNode', required=False)

    primary_orgs = graphene.List('orgs.schema.OrganizationNode', required=True)

    admin_url = graphene.String(required=False)
    view_url = graphene.String(client_url=graphene.String(required=False))

    main_menu = pages_schema.MainMenuNode.create_plan_menu_field()
    footer = pages_schema.FooterNode.create_plan_menu_field()
    additional_links = pages_schema.AdditionalLinksNode.create_plan_menu_field()

    # FIXME: Legacy attributes, remove later
    hide_action_identifiers = graphene.Boolean()
    hide_action_official_name = graphene.Boolean()
    hide_action_lead_paragraph = graphene.Boolean()

    features = graphene.Field(PlanFeaturesNode, required=True)
    general_content = graphene.Field('aplans.schema.SiteGeneralContentNode', required=True)
    all_related_plans = graphene.List('actions.schema.PlanNode', required=True)

    action_update_target_interval = graphene.Int()
    action_update_acceptable_interval = graphene.Int()

    superseding_plans = graphene.List(
        graphene.NonNull('actions.schema.PlanNode'),
        recursive=graphene.Boolean(default_value=False),
        required=True,
    )
    superseded_plans = graphene.List(
        graphene.NonNull('actions.schema.PlanNode'),
        recursive=graphene.Boolean(default_value=False),
        required=True,
    )
    action_status_summaries = graphene.List(
        graphene.NonNull('actions.schema.ActionStatusSummaryNode'), required=True
    )
    action_timeliness_classes = graphene.List(
        graphene.NonNull('actions.schema.ActionTimelinessNode'), required=True
    )

    has_indicator_relationships = graphene.Boolean()

    @staticmethod
    def resolve_action_status_summaries(root: Plan, info):
        return list(a.get_data({'plan': root}) for a in ActionStatusSummaryIdentifier)

    @staticmethod
    def resolve_action_timeliness_classes(root: Plan, info):
        return list(a.get_data({'plan': root}) for a in ActionTimelinessIdentifier)

    @staticmethod
    def resolve_last_action_identifier(root: Plan, info):
        return root.get_last_action_identifier()

    @staticmethod
    def resolve_category_type(root: Plan, info, id):
        return root.category_types.get(id=id)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='category_types',
    )
    def resolve_category_types(root: Plan, info, usable_for_indicators=None, usable_for_actions=None):
        qs = root.category_types.all()
        if usable_for_indicators is not None:
            qs = qs.filter(usable_for_indicators=usable_for_indicators)
        if usable_for_indicators is not None:
            qs = qs.filter(usable_for_indicators=usable_for_indicators)
        return qs.order_by('pk')

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='impact_groups',
    )
    def resolve_impact_groups(root: Plan, info, first=None):
        qs = root.impact_groups.all()
        if first is not None:
            qs = qs[0:first]
        return qs.order_by('pk')

    @staticmethod
    def resolve_serve_file_base_url(root: Plan, info):
        request = info.context
        return request.build_absolute_uri('/').rstrip('/')

    @staticmethod
    def resolve_pages(root: Plan, info: GQLInfo):
        root_page: Page | None = root.root_page
        if not root_page:
            return
        return root_page.get_descendants(inclusive=True).live().public().type(AplansPage).specific()

    @staticmethod
    def resolve_action_list_page(root: Plan, info: GQLInfo):
        root_page: Page | None = root.get_translated_root_page()
        if not root_page:
            return
        return root_page.get_descendants().live().public().type(ActionListPage).first().specific

    @staticmethod
    def resolve_view_url(root: Plan, info, client_url: Optional[str] = None):
        if client_url:
            try:
                urlparse(client_url)
            except Exception:
                raise GraphQLError('clientUrl must be a valid URL')
        return root.get_view_url(client_url=client_url)

    @staticmethod
    def resolve_admin_url(root: Plan, info):
        if not root.features.show_admin_link:
            return None
        client_plan = root.clients.first()
        if client_plan is None:
            return None
        return client_plan.client.get_admin_url()

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='actions',
    )
    def resolve_actions(
            root: Plan,
            info: GQLInfo,
            identifier=None,
            id=None,
            only_mine=False,
            restrict_to_publicly_visible=True,
            responsible_organization=None,
            first: int | None = None
    ):
        user = info.context.user
        qs = root.actions.get_queryset()
        if restrict_to_publicly_visible:
            qs = qs.visible_for_public()
        else:
            qs = qs.visible_for_user(user)
        qs = qs.filter(plan=root)
        if identifier:
            qs = qs.filter(identifier=identifier)
        if id:
            qs = qs.filter(id=id)
        if only_mine:
            if not user.is_authenticated or not user.is_staff:
                qs = qs.none()
            else:
                qs = qs.user_has_staff_role_for(user, plan=root)
        if responsible_organization:
            qs = qs.filter(responsible_organizations=responsible_organization)

        if first is not None and first > 0:
            qs = qs[0:first]

        return qs

    @staticmethod
    def resolve_action_attribute_types(root: Plan, info):
        return root.action_attribute_types.order_by('pk')

    @staticmethod
    def resolve_primary_orgs(root: Plan, info):
        qs = Action.objects.filter(plan=root).values_list('primary_org').distinct()
        return Organization.objects.filter(id__in=qs)

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('features',),
    )
    def resolve_hide_action_identifiers(root: Plan, info):
        return not root.features.show_action_identifiers

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('features',)
    )
    def resolve_hide_action_lead_paragraph(root: Plan, info):
        return not root.features.has_action_lead_paragraph

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('features',)
    )
    def resolve_hide_action_official_name(root: Plan, info):
        return not root.features.has_action_official_name

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('parent',),
    )
    def resolve_all_related_plans(root: Plan, info):
        return root.get_all_related_plans()

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('image',),
        only=('image',)
    )
    def resolve_image(root: Plan, info):
        return root.image

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('primary_action_classification',),
        only=('primary_action_classification',)
    )
    def resolve_primary_action_classification(root: Plan, info):
        return root.primary_action_classification

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('secondary_action_classification',),
        only=('secondary_action_classification',)
    )
    def resolve_secondary_action_classification(root: Plan, info):
        return root.secondary_action_classification

    @staticmethod
    def resolve_action_update_target_interval(root: Plan, info):
        return root.action_update_target_interval

    @staticmethod
    def resolve_action_update_acceptable_interval(root: Plan, info):
        return root.action_update_acceptable_interval

    @staticmethod
    def resolve_superseding_plans(root: Plan, info, recursive=False):
        return root.get_superseding_plans(recursive)

    @staticmethod
    def resolve_superseded_plans(root: Plan, info, recursive=False):
        return root.get_superseded_plans(recursive)

    @staticmethod
    def resolve_has_indicator_relationships(root: Plan, info):
        return root.has_indicator_relationships()


    class Meta:
        model = Plan
        interfaces = (PlanInterface,)
        fields = public_fields(Plan)


AttributeObject = typing.Union[
    AttributeCategoryChoice, AttributeChoiceModel, AttributeChoiceWithText,
    AttributeText, AttributeRichText, AttributeNumericValue,
]


class AttributeInterface(graphene.Interface):
    id = graphene.ID(required=True)
    type_ = graphene.Field('actions.schema.AttributeTypeNode', name='type', required=True)
    key = graphene.String(required=True)
    key_identifier = graphene.String(required=True)

    @staticmethod
    def resolve_key(root: AttributeObject, info):
        return root.type.name

    @staticmethod
    def resolve_key_identifier(root: AttributeObject, info):
        return root.type.identifier

    @staticmethod
    def resolve_id(root, info):
        return getattr(root, 'pk', None) or f'unpublished-{uuid.uuid4()}'

    @staticmethod
    def resolve_type_(root: AttributeObject, info) -> AttributeType:
        return root.type

    @classmethod
    def resolve_type(cls, instance, info):
        if isinstance(instance, AttributeText):
            return AttributeTextNode
        elif isinstance(instance, AttributeRichText):
            return AttributeRichTextNode
        elif isinstance(instance, (AttributeChoiceModel, AttributeChoiceWithText)):
            return AttributeChoice
        elif isinstance(instance, AttributeNumericValue):
            return AttributeNumericValueNode
        elif isinstance(instance, AttributeCategoryChoice):
            return AttributeCategoryChoiceNode


@register_graphene_node
class AttributeChoice(graphene.ObjectType):
    id = graphene.ID(required=True)
    choice = graphene.Field(
        'actions.schema.AttributeTypeChoiceOptionNode', required=False
    )
    text = graphene.String(required=False)

    def resolve_id(self, info):
        if isinstance(self, AttributeChoiceModel):
            prefix = 'C'
        else:
            prefix = 'CT'
        return f'{prefix}{self.id}'

    def resolve_text(self, info):
        return getattr(self, 'text_i18n', None)

    class Meta:
        interfaces = (AttributeInterface,)


@register_django_node
class AttributeTextNode(DjangoNode):
    value = graphene.String(required=True)

    @staticmethod
    def resolve_value(root: AttributeText, info):
        return root.text_i18n

    class Meta:
        model = AttributeText
        interfaces = (AttributeInterface,)
        # We expose `value` instead of `text`
        fields = public_fields(AttributeText, remove_fields=['text'])


@register_django_node
class AttributeRichTextNode(DjangoNode):
    value = graphene.String(required=True)

    @staticmethod
    def resolve_value(root: AttributeRichText, info):
        return root.text_i18n

    class Meta:
        model = AttributeRichText
        interfaces = (AttributeInterface,)
        # We expose `value` instead of `text`
        fields = public_fields(AttributeRichText, remove_fields=['text'])


@register_django_node
class AttributeCategoryChoiceNode(DjangoNode):
    class Meta:
        model = AttributeCategoryChoice
        interfaces = (AttributeInterface,)
        fields = public_fields(AttributeCategoryChoice)


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


class HasLeadParagraph(Protocol):
    lead_paragraph: str | None


# TODO: Remove this when production UI is updated
class ResolveShortDescriptionFromLeadParagraphShim:
    short_description = graphene.String()

    @staticmethod
    def resolve_short_description(root: HasLeadParagraph, info):
        return root.lead_paragraph


@register_django_node
class CategoryTypeNode(ResolveShortDescriptionFromLeadParagraphShim, DjangoNode):
    attribute_types = graphene.List(graphene.NonNull(AttributeTypeNode), required=True)
    selection_type = convert_django_field_with_choices(CategoryType._meta.get_field('select_widget'))
    categories = graphene.List(
        graphene.NonNull('actions.schema.CategoryNode'),
        only_root=graphene.Boolean(default_value=False),
        only_with_actions=graphene.Boolean(default_value=False),
        required=True
    )

    class Meta:
        model = CategoryType
        fields = public_fields(CategoryType, remove_fields=['select_widget'])

    @staticmethod
    def resolve_attribute_types(root: CategoryType, info):
        return root.attribute_types.order_by('pk')

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='select_widget',
    )
    def resolve_selection_type(root: CategoryType, info):
        return root.select_widget

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='categories',
    )
    def resolve_categories(root: CategoryType, info, only_root: bool, only_with_actions: bool):
        qs = root.categories.all()
        if only_with_actions:
            with_actions = set()
            categories = {cat.pk: cat for cat in qs.prefetch_related('actions')}
            for cat in categories.values():
                if cat.actions.count() == 0:
                    continue
                with_actions.add(cat)
                parent_pk = cat.parent_id
                while parent_pk is not None:
                    parent = categories[parent_pk]
                    with_actions.add(parent)
                    parent_pk = parent.parent_id
            if only_root:
                return [c for c in with_actions if c.parent_id is None]
            return list(with_actions)
        if only_root:
            qs = qs.filter(parent__isnull=True)
        return qs


@register_django_node
class CommonCategoryTypeNode(ResolveShortDescriptionFromLeadParagraphShim, DjangoNode):
    class Meta:
        model = CommonCategoryType
        fields = public_fields(CommonCategoryType)


def get_translated_category_page(info, **kwargs) -> Prefetch:
    qs = CategoryPage.objects.filter(locale__language_code__iexact=get_language())
    return Prefetch('category_pages', to_attr='category_pages_locale', queryset=qs)


def prefetch_workflow_states(info, **_kwargs) -> Prefetch:
    workflow_states = WorkflowState.objects.active().select_related(
        "current_task_state__task"
    )
    return Prefetch(
        "_workflow_states",
        queryset=workflow_states,
        to_attr="_current_workflow_states",
    )


class AttributesMixin:
    attributes = graphene.List(graphene.NonNull(AttributeInterface), id=graphene.ID(required=False), required=True)

    @staticmethod
    @gql_optimizer.resolver_hints(
        prefetch_related=[
            *chain(*[(f'{rel}__type', f'{rel}__content_object') for rel in ModelWithAttributes.ATTRIBUTE_RELATIONS]),
            *['choice_attributes__choice__type', 'choice_with_text_attributes__choice__type'],
        ]
    )
    def resolve_attributes(root: Category | Action, info: GQLInfo, id: str | None = None):
        request = info.context
        plan = get_plan_from_context(info)

        def filter_attrs(attributes: Iterable[Attribute]) -> list[Attribute]:
            result = []
            for attribute in attributes:
                id_mismatch = id is not None and attribute.type.identifier != id
                if not id_mismatch and attribute.is_visible_for_user(request.user, plan):
                    result.append(attribute)
            return result

        attributes: list[Attribute] = []
        if root.draft_attributes:
            cache = info.context.watch_cache.for_plan(plan)
            attribute_types = root.get_visible_attribute_types(request.user)
            for attribute_type in attribute_types:
                try:
                    attribute_value = root.draft_attributes.get_value_for_attribute_type(attribute_type)
                except KeyError:
                    message = (
                        f"Could not get value for attribute type {attribute_type.instance.pk} on "
                        f"{root._meta.model.__name__} {root.id}; skipping this attribute type"
                    )
                    logger.warning(message)
                    sentry_sdk.capture_message(message)
                    continue
                instance = attribute_value.instantiate_attribute(attribute_type, root)
                attributes.append(instance)
        else:
            for relation_name in ModelWithAttributes.ATTRIBUTE_RELATIONS:
                attributes += filter_attrs(getattr(root, relation_name).all())
        return sorted(attributes, key=lambda a: a.type.order)


@register_django_node
class CategoryNode(ResolveShortDescriptionFromLeadParagraphShim, AttributesMixin, DjangoNode):
    image = graphene.Field('images.schema.ImageNode')
    attributes = graphene.List(graphene.NonNull(AttributeInterface), id=graphene.ID(required=False))
    level = graphene.Field(CategoryLevelNode)
    actions = graphene.List(graphene.NonNull('actions.schema.ActionNode'))
    icon_image = graphene.Field('images.schema.ImageNode')
    icon_svg_url = graphene.String()
    category_page = graphene.Field(grapple_registry.pages[CategoryPage])
    datasets = graphene.List('budget.schema.DatasetNode')

    @staticmethod
    def _resolve_field_with_fallback_to_common(root: Category, field_name: str):
        value = getattr(root, field_name)
        if value or root.common is None:
            return value
        return getattr(root.common, field_name)

    @staticmethod
    def resolve_image(root: Category, info):
        return CategoryNode._resolve_field_with_fallback_to_common(root, 'image')

    @staticmethod
    def resolve_level(root: Category, info):
        depth = 0
        obj = root
        # Uh oh, Category is not a tree model yet
        while obj.parent is not None:
            obj = obj.parent
            depth += 1
            if depth == 5:
                break

        levels = list(root.type.levels.all())
        if depth >= len(levels):
            return None
        return levels[depth]

    @staticmethod
    def resolve_actions(root: Category, info) -> ActionQuerySet:
        return root.actions.get_queryset().visible_for_user(info.context.user)

    @staticmethod
    @gql_optimizer.resolver_hints(
        prefetch_related=get_translated_category_page
    )
    def resolve_category_page(root: Category, info):
        # If we have prefetched the page in the right locale, use that
        if hasattr(root, 'category_pages_locale'):
            pages = root.category_pages_locale
            if not len(pages):
                return None
            return pages[0]

        try:
            return root.category_pages.get(locale__language_code__iexact=get_language())
        except CategoryPage.DoesNotExist:
            return None

    @staticmethod
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

    @staticmethod
    @gql_optimizer.resolver_hints(
        prefetch_related=('icons',),
        select_related=('common',),
        only=('common',)
    )
    def resolve_icon_svg_url(root: Category, info):
        icon = root.get_icon(get_language())
        if icon and icon.image.filename.endswith('.svg'):
            return info.context.build_absolute_uri(icon.image.file.url)
        return None

    @staticmethod
    def resolve_help_text(root: Category, info):
        return CategoryNode._resolve_field_with_fallback_to_common(root, 'help_text_i18n')

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='lead_paragraph',
        select_related=('type__plan'),
        only=('lead_paragraph', 'i18n', 'type__plan__primary_language',
              'type__plan__primary_language_lowercase'),
    )
    def resolve_lead_paragraph(root: Category, info):
        return CategoryNode._resolve_field_with_fallback_to_common(root, 'lead_paragraph_i18n')

    @staticmethod
    def resolve_datasets(root: Category, info):
        category_content_type = ContentType.objects.get_for_model(Category)
        dataset_ids = DatasetScope.objects.filter(
            scope_content_type=category_content_type,
            scope_id=root.id
        ).values_list('dataset_id', flat=True)
        return Dataset.objects.filter(id__in=dataset_ids)

    class Meta:
        model = Category
        fields = public_fields(Category, add_fields=['level', 'icon_image', 'icon_svg_url'])


@register_django_node
class CommonCategoryNode(ResolveShortDescriptionFromLeadParagraphShim, DjangoNode):
    icon_image = graphene.Field('images.schema.ImageNode')
    icon_svg_url = graphene.String()
    category_instances = graphene.List(graphene.NonNull(CategoryNode), required=True)

    @staticmethod
    def resolve_icon_image(root, info):
        icon = root.get_icon(get_language())
        if icon:
            return icon.image
        return None

    @staticmethod
    def resolve_icon_svg_url(root, info):
        icon = root.get_icon(get_language())
        if icon and icon.image.filename.endswith('.svg'):
            return info.context.build_absolute_uri(icon.image.file.url)
        return None

    @staticmethod
    def resolve_category_instances(root: CommonCategory, info: GQLInfo):
        return root.category_instances.filter(type__plan=Plan.objects.available_for_request(info.context))

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
        fields = public_fields(ImpactGroupAction)


class MonitoringQualityPointNode(DjangoNode):
    name = graphene.String()
    description_yes = graphene.String()
    description_no = graphene.String()

    class Meta:
        model = MonitoringQualityPoint
        fields = public_fields(MonitoringQualityPoint)


class ActionTaskNode(DjangoNode):
    class Meta:
        model = ActionTask
        fields = public_fields(ActionTask)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='comment',
    )
    def resolve_comment(root: ActionTask, info):
        root.i18n  # Workaround to avoid i18n field being deferred in gql_optimizer
        comment = root.comment_i18n
        if comment is None:
            return None

        return RichText(comment)


ActionStatusSummaryIdentifierNode = graphene.Enum.from_enum(ActionStatusSummaryIdentifier)
ActionTimelinessIdentifierNode = graphene.Enum.from_enum(ActionTimelinessIdentifier)
Sentiment = graphene.Enum.from_enum(SentimentEnum)


@register_graphene_node
class ActionStatusSummaryNode(graphene.ObjectType):
    identifier = ActionStatusSummaryIdentifierNode(required=True)
    label = graphene.String(required=True)
    color = graphene.String(
        required=True,
        deprecation_reason='This field is an internal implementation detail; most often you should use action.color'
    )
    is_active = graphene.Boolean(required=True)
    is_completed = graphene.Boolean(required=True)
    sentiment = Sentiment(required=True)

    class Meta:
        name = 'ActionStatusSummary'


@register_graphene_node
class ActionTimelinessNode(graphene.ObjectType):
    identifier = ActionTimelinessIdentifierNode(required=True)
    label = graphene.String(required=True, deprecation_reason='Generate human-friendly labels in the UI.')
    color = graphene.String(required=True)
    sentiment = Sentiment(required=True)
    comparison = graphene.Enum.from_enum(Comparison)(required=True)
    days = graphene.Int(required=True)

    class Meta:
        name = 'ActionTimeliness'


@register_django_node
class ActionDependencyRoleNode(DjangoNode):
    class Meta:
        model = ActionDependencyRole
        fields = ActionDependencyRole.public_fields


@register_django_node
class ActionDependencyRelationshipNode(DjangoNode):
    class Meta:
        model = ActionDependencyRelationship
        fields = ActionDependencyRelationship.public_fields


def _get_visible_action(root, field_name, user: Optional[User]):
    action_id = getattr(root, f'{field_name}_id')
    if action_id is None:
        return None
    try:
        retval = Action.objects.get_queryset().visible_for_user(user).get(id=action_id)
    except Action.DoesNotExist:
        return None
    return retval


def _get_visible_actions(root, field_name, user: Optional[User]):
    actions = getattr(root, field_name)
    return actions.visible_for_user(user)


class RevisionNode(DjangoNode):
    class Meta:
        model = Revision
        fields = ('created_at',)


class WorkflowStateInfoNode(DjangoNode):
    status_message = graphene.String()
    class Meta:
        model = WorkflowState
        fields = ('status',)

    @staticmethod
    def resolve_status_message(root: WorkflowState, info: GQLInfo) -> str | None:
        status_choices = dict(WorkflowState.STATUS_CHOICES)
        return status_choices.get(root.status)


class WorkflowInfoNode(graphene.ObjectType):
    has_unpublished_changes = graphene.Boolean(default_value=False)
    latest_revision = graphene.Field('actions.schema.RevisionNode')
    current_workflow_state = graphene.Field(
        'actions.schema.WorkflowStateInfoNode',
        description=(
            "The internal Wagtail workflow state of the action. "
            "The current action data returned does not necessarily match this "
            "workflowstate."
        )
    )
    matching_version = graphene.Field(
        WorkflowStateDescription,
        description=(
            "The actual version of the action returned "
            "when fulfilling this query, based on both the requested workflow directive value used when querying "
            "an action, and the available versions of the action itself."
        )
    )

    @staticmethod
    def resolve_has_unpublished_changes(root: Action, info: GQLInfo) -> bool:
        return root.has_unpublished_changes

    @staticmethod
    def resolve_latest_revision(root: Action, info: GQLInfo) -> Revision:
        return root.get_latest_revision()

    @staticmethod
    def resolve_current_workflow_state(root: Action, info: GQLInfo) -> WorkflowState:
        return root.current_workflow_state

    @staticmethod
    def resolve_matching_version(root: Action, info: GQLInfo) -> dict[str, str]:
        def make_result(match: WorkflowStateEnum | None) -> dict[str, str]:
            return dict(
                id=match.name,
                description=WorkflowStateEnum(match).description
            )
        return make_result(getattr(root, '_actual_workflow_state', WorkflowStateEnum.PUBLISHED))


@register_django_node
class ActionNode(AdminButtonsMixin, AttributesMixin, DjangoNode):
    ORDERABLE_FIELDS = ['updated_at', 'identifier']

    name = graphene.String(hyphenated=graphene.Boolean(), required=True)
    categories = graphene.List(graphene.NonNull(CategoryNode), category_type=graphene.ID(), required=True)
    contact_persons = graphene.List(
        graphene.NonNull('actions.schema.ActionContactPersonNode'),
        required=True,
        show_all_contact_persons=graphene.Boolean(default_value=False))
    next_action = graphene.Field('actions.schema.ActionNode')
    previous_action = graphene.Field('actions.schema.ActionNode')
    image = graphene.Field('images.schema.ImageNode')
    view_url = graphene.String(client_url=graphene.String(required=False), required=True)
    edit_url = graphene.String()
    similar_actions = graphene.List('actions.schema.ActionNode')
    status_summary = graphene.Field('actions.schema.ActionStatusSummaryNode', required=True)
    timeliness = graphene.Field('actions.schema.ActionTimelinessNode', required=True)
    color = graphene.String(required=False)
    all_dependency_relationships = graphene.List(
        graphene.NonNull('actions.schema.ActionDependencyRelationshipNode'), required=True
    )
    workflow_status = graphene.Field('actions.schema.WorkflowInfoNode')

    indicators_count = graphene.Int()
    has_indicators_with_goals = graphene.Boolean()

    datasets = graphene.List('budget.schema.DatasetNode')

    class Meta:
        model = Action
        fields = Action.public_fields

    @staticmethod
    def resolve_merged_with(root: Action, info):
        return _get_visible_action(root, 'merged_with', info.context.user)

    @staticmethod
    def resolve_superseded_by(root: Action, info):
        return _get_visible_action(root, 'superseded_by', info.context.user)

    @staticmethod
    def resolve_merged_actions(root: Action, info):
        return _get_visible_actions(root, 'merged_actions', info.context.user)

    @staticmethod
    def resolve_superseded_actions(root: Action, info):
        return _get_visible_actions(root, 'superseded_actions', info.context.user)

    @staticmethod
    def resolve_related_actions(root: Action, info):
        return _get_visible_actions(root, 'related_actions', info.context.user)

    @staticmethod
    def resolve_next_action(root: Action, info):
        return root.get_next_action(info.context.user)

    @staticmethod
    def resolve_previous_action(root: Action, info):
        return root.get_previous_action(info.context.user)
    
    @gql_optimizer.resolver_hints(
        model_field='related_indicators',
    )
    def resolve_related_indicators(root: Action, info):
        plan = root.plan
        return root.get_visible_related_indicators().order_by_setting(plan)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='name',
        select_related=('plan'),
        only=('name', 'i18n', 'plan__primary_language', 'plan__primary_language_lowercase'),
    )
    def resolve_name(root: Action, info, hyphenated=False):
        name = root.name_i18n
        if name is None:
            return None
        language: str | None = get_language()
        if language:
            language = language.lower()
        if hyphenated and language == 'fi':
            name = hyphenate_fi(name)
        return name

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('description', 'i18n'),
    )
    def resolve_description(root: Action, info):
        description = root.description_i18n
        if description is None:
            return None
        return RichText(description)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('lead_paragraph', 'i18n', 'plan__primary_language', 'plan__primary_language_lowercase'),
    )
    def resolve_lead_paragraph(root: Action, info):
        return root.lead_paragraph_i18n

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('plan', 'identifier')
    )
    def resolve_view_url(root: Action, info, client_url: Optional[str] = None):
        return root.get_view_url(client_url=client_url)

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('status', 'implementation_phase'),
        only=('plan', 'merged_with', 'status__color',
              'status__identifier', 'implementation_phase__color', 'implementation_phase__identifier'),
    )
    def resolve_color(root: Action, info: GQLInfo):
        return root.get_color(cache=info.context.watch_cache)

    @staticmethod
    def resolve_edit_url(root: Action, info):
        client_plan = root.plan.clients.first()
        if client_plan is None:
            return None
        base_url = client_plan.client.get_admin_url().rstrip('/')
        url_helper = ActionAdmin().url_helper
        edit_url = url_helper.get_action_url('edit', root.id).lstrip('/')
        return f'{base_url}/{edit_url}'

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='categories',
    )
    def resolve_categories(root: Action, info: GQLInfo, category_type=None):
        qs = root.categories.all()
        if category_type is not None:
            qs = qs.filter(type__identifier=category_type)
        return qs

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='contact_persons',
        prefetch_related='contact_persons__person'
    )
    def resolve_contact_persons(root: Action, info: GQLInfo, show_all_contact_persons: bool):
        plan: Plan = get_plan_from_context(info)
        user = info.context.user
        acps = []
        cache = info.context.watch_cache.for_plan(plan)
        for acp in root.contact_persons.all():
            person = cache.get_person(acp.person_id) or acp.person
            if not person.visible_for_user(user=user, plan=plan):
                continue
            acps.append(acp)
        if plan.features.contact_persons_hide_moderators and (
            not show_all_contact_persons or not user.is_authenticated or not user.can_access_admin(plan)):
            acps = [acp for acp in acps if not acp.is_moderator()]
        return acps

    @staticmethod
    def resolve_similar_actions(root: Action, info):
        backend = get_search_backend()
        if backend is None:
            return []
        backend.more_like_this(root)
        return []

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('merged_with',),
        select_related=('status', 'implementation_phase',),
    )
    def resolve_status_summary(root: Action, info: GQLInfo):
        return root.get_status_summary(cache=info.context.watch_cache)

    @staticmethod
    def resolve_timeliness(root: Action, info):
        return root.get_timeliness()

    @staticmethod
    def resolve_all_dependency_relationships(root: Action, info: GQLInfo):
        cache = info.context.watch_cache.for_plan_id(root.plan_id)
        if not cache.plan_has_action_dependency_roles:
            return []
        return root.get_dependency_relationships(info.context.user, root.plan)

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('latest_revision','plan'),
        only=('latest_revision', 'has_unpublished_changes', 'plan', 'plan__features__moderation_workflow'),
        prefetch_related=prefetch_workflow_states
    )
    def resolve_workflow_status(root: Action, info) -> WorkflowState | None:
        user = info.context.user
        plan = root.plan
        if not user.is_authenticated or not user.can_access_public_site(plan):
            return None
        return root

    @staticmethod
    def resolve_indicators_count(root: Action, info):
        inds_count = getattr(root, 'indicator_count', 0)
        return inds_count

    @staticmethod
    def resolve_has_indicators_with_goals(root: Action, info):
        goals_count = getattr(root, 'indicators_with_goals_count', 0)
        return goals_count > 0

    @staticmethod
    def resolve_datasets(root: Action, info):
        action_content_type = ContentType.objects.get_for_model(Action)
        dataset_ids = DatasetScope.objects.filter(
            scope_content_type=action_content_type,
            scope_id=root.id
        ).values_list('dataset_id', flat=True)
        return Dataset.objects.filter(id__in=dataset_ids)

class ActionScheduleNode(DjangoNode):
    class Meta:
        model = ActionSchedule
        fields = public_fields(ActionSchedule)


class ActionStatusNode(DjangoNode):
    class Meta:
        model = ActionStatus
        fields = public_fields(ActionStatus, add_fields=['color'])

    @staticmethod
    def resolve_color(root: ActionStatus, info: GQLInfo):
        return root.get_color(cache=info.context.watch_cache)


class ActionImplementationPhaseNode(DjangoNode):
    class Meta:
        model = ActionImplementationPhase
        fields = public_fields(ActionImplementationPhase)


class ActionResponsiblePartyNode(DjangoNode):
    @staticmethod
    def resolve_organization(root: ActionResponsibleParty, info) -> Organization:
        cache = info.context.watch_cache.for_plan_id(root.action.plan_id)
        return cache.get_organization(root.organization_id) or root.organization

    class Meta:
        model = ActionResponsibleParty
        fields = public_fields(ActionResponsibleParty)


class ActionContactPersonNode(DjangoNode):
    @staticmethod
    def resolve_person(root: ActionContactPerson, info) -> Person:
        cache = info.context.watch_cache.for_plan_id(root.action.plan_id)
        person = cache.get_person(root.person_id) or root.person
        person_organization = cache.get_organization(person.organization_id)
        if person_organization is not None:
            person.organization = person_organization
        return person

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

    @staticmethod
    def resolve_url(root: ActionLink, info):
        return root.url_i18n

    @staticmethod
    def resolve_title(root: ActionLink, info):
        return root.title_i18n


def plans_actions_queryset(plans, category, first, order_by, user, restrict_to_publicly_visible=True):
    qs = Action.objects.get_queryset()
    if restrict_to_publicly_visible:
        qs = qs.visible_for_public()
    else:
        qs = qs.visible_for_user(user)
    qs = qs.filter(plan__in=plans)
    if category is not None:
        # FIXME: This is sucky, maybe convert Category to a proper tree model?
        f = (
            Q(id=category) |
            Q(parent=category) |
            Q(parent__parent=category) |
            Q(parent__parent__parent=category) |
            Q(parent__parent__parent__parent=category)
        )
        descendant_cats = Category.objects.filter(f)
        qs = qs.filter(categories__in=descendant_cats).distinct()
    if isinstance(plans, list) and len(plans) == 1:
        plan = plans[0]
        qs = qs.annotate_related_indicator_counts(plan)
    qs = order_queryset(qs, ActionNode, order_by)
    if not order_by:
        qs = qs.order_by('plan', 'order')
    if first is not None:
        qs = qs[0:first]
    return qs


def _resolve_published_action(
        obj_id: int | None,
        identifier: str | None,
        plan_identifier: str | None,
        info
) -> Action | None:
    qs = Action.objects.get_queryset().visible_for_user(info.context.user).all()
    if obj_id:
        qs = qs.filter(id=obj_id)
    if identifier:
        plan_obj = get_plan_from_context(info, plan_identifier)
        if not plan_obj:
            raise GraphQLError("You must supply the 'plan' argument when using 'identifier'")
        qs = qs.filter(identifier=identifier, plan=plan_obj)
    qs = gql_optimizer.query(qs, info)

    try:
        return qs.get()
    except Action.DoesNotExist:
        return None


def _resolve_action_revision(action: Action, desired_workflow_state: WorkflowStateEnum):
    def with_workflow_state(match: WorkflowStateEnum, action: Action) -> Action:
        assert match != WorkflowStateEnum.PUBLISHED
        revision = action.latest_revision
        revision_action = revision.as_object()
        revision_action.updated_at = revision.created_at
        revision_action._actual_workflow_state = match
        return revision_action

    def published(action: Action):
        action._actual_workflow_state = WorkflowStateEnum.PUBLISHED
        return action

    current_progress, max_progress = action.get_workflow_progress()

    if current_progress == max_progress:
        return published(action)

    available_revision_state = WorkflowStateEnum.DRAFT
    if current_progress > 1:
        available_revision_state = WorkflowStateEnum.APPROVED

    if desired_workflow_state == WorkflowStateEnum.DRAFT:
        return with_workflow_state(available_revision_state, action)
    if desired_workflow_state == WorkflowStateEnum.APPROVED:
        if available_revision_state == WorkflowStateEnum.APPROVED:
            return with_workflow_state(available_revision_state, action)

    # User wants published version or no other appropriate version available
    return published(action)


class Query:
    plan = gql_optimizer.field(graphene.Field(PlanNode, id=graphene.ID(), domain=graphene.String()))
    plans_for_hostname = graphene.List(PlanInterface, hostname=graphene.String())
    my_plans = graphene.List(PlanNode)

    action = graphene.Field(ActionNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())

    plan_actions = graphene.List(
        graphene.NonNull(ActionNode), plan=graphene.ID(required=True), first=graphene.Int(),
        category=graphene.ID(), order_by=graphene.String(), restrict_to_publicly_visible=graphene.Boolean(default_value=True),
    )
    related_plan_actions = graphene.List(
        graphene.NonNull(ActionNode), plan=graphene.ID(required=True), first=graphene.Int(),
        category=graphene.ID(), order_by=graphene.String(),
    )
    plan_categories = graphene.List(
        CategoryNode, plan=graphene.ID(required=True), category_type=graphene.ID()
    )

    category = graphene.Field(
        CategoryNode, plan=graphene.ID(required=True), category_type=graphene.ID(required=True),
        external_identifier=graphene.ID(required=True)
    )

    workflow_states = graphene.List(
        WorkflowStateDescription, plan=graphene.ID(required=False)
    )

    @staticmethod
    def resolve_workflow_states(root, info, plan):
        if plan is None:
            return []
        user = info.context.user
        result = []
        plan = Plan.objects.get(identifier=plan)
        if plan.features.moderation_workflow is None:
            return []
        tasks = plan.get_workflow_tasks()
        if not user.is_authenticated or not user.can_access_public_site(plan):
            result = [WorkflowStateEnum.PUBLISHED]
        elif user.can_access_admin(plan):
            if tasks.count() > 1:
                result = [WorkflowStateEnum.PUBLISHED, WorkflowStateEnum.APPROVED, WorkflowStateEnum.DRAFT]
            else:
                result = [WorkflowStateEnum.PUBLISHED, WorkflowStateEnum.DRAFT]
        elif user.can_access_public_site(plan):
            if tasks.count() > 1:
                result = [WorkflowStateEnum.PUBLISHED, WorkflowStateEnum.DRAFT]
            else:
                result = [WorkflowStateEnum.PUBLISHED]
        return [{
            'id': e.name,
            'description': WorkflowStateEnum(e).description,
        } for e in result]


    @staticmethod
    def resolve_plan(root, info: GQLInfo, id=None, domain=None, **kwargs):
        if not id and not domain:
            raise GraphQLError("You must supply either id or domain as arguments to 'plan'")

        qs = Plan.objects.all()
        if id:
            qs = qs.filter(identifier=id.lower())
        if domain:
            qs = qs.for_hostname(domain.lower(), request=info.context)
            info.context._plan_hostname = domain

        plan = gql_optimizer.query(qs, info).first()
        if not plan:
            return None

        set_active_plan(info, plan)
        return plan

    @staticmethod
    def resolve_plans_for_hostname(root, info: GQLInfo, hostname: str):
        info.context._plan_hostname = hostname
        plans = Plan.objects.for_hostname(hostname.lower(), request=info.context)
        return list(gql_optimizer.query(plans, info))

    @staticmethod
    def resolve_my_plans(root, info: GQLInfo):
        user = info.context.user
        if user is None:
            return []
        plans = Plan.objects.user_has_staff_role_for(info.context.user)
        return gql_optimizer.query(plans, info)

    @staticmethod
    def _resolve_plan_action_revisions(
            plan: Plan,
            desired_workflow_state: WorkflowStateEnum,
            action_queryset: ActionQuerySet,
            cache: PlanSpecificCache
    ):
        ct = ContentType.objects.get_for_model(Action)
        revision_pks = []
        actions_without_revision = []
        if desired_workflow_state == WorkflowStateEnum.DRAFT:
            revision_pks = action_queryset.filter(has_unpublished_changes=True).values_list('latest_revision_id', flat=True)
            actions_without_revision = action_queryset.filter(has_unpublished_changes=False)
        elif desired_workflow_state == WorkflowStateEnum.APPROVED:
            desired_workflow_task = plan.get_next_workflow_task(desired_workflow_state)
            action_pks = [str(pk) for pk in action_queryset.values_list('pk', flat=True)]
            if desired_workflow_task is not None:
                workflowstates = (
                    WorkflowState.objects.active()\
                    .filter(content_type=ct)\
                    .filter(current_task_state__task=desired_workflow_task)\
                    .filter(object_id__in=action_pks)
                )
                actions_with_revision_pks = workflowstates.values_list('object_id', flat=True)
                actions_without_revision = action_queryset.exclude(pk__in=[int(pk) for pk in actions_with_revision_pks])
                revision_pks = workflowstates.values_list('current_task_state__revision_id', flat=True)
        revision_qs = Revision.objects.filter(pk__in=revision_pks).prefetch_related('content_object__plan')
        actions = []
        for rev in revision_qs:
            content = SerializedDictWithRelatedObjectCache(rev.content, cache=cache)
            action = Action.from_serializable_data(content, check_fks=False, strict_fks=False)
            if action is not None:
                cache.enrich_action(action)
                actions.append(action)
        prefetch_related_objects(
            actions,
            'schedule',
            'indicators__goals',
            'categories',
        )
        actions.extend(actions_without_revision)
        return sorted(actions, key=lambda o: o.order)

    @staticmethod
    def resolve_plan_actions(root, info, plan, first=None, category=None, order_by=None, restrict_to_publicly_visible=True, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None
        workflow_state = info.context.watch_cache.query_workflow_state
        qs = gql_optimizer.query(
            plans_actions_queryset(
                [plan_obj],
                category,
                first,
                order_by,
                info.context.user,
                restrict_to_publicly_visible=restrict_to_publicly_visible
            ),
            info
        )
        user = info.context.user
        cache = info.context.watch_cache.for_plan(plan_obj)
        persons_queryset = Person.objects.filter(actioncontactperson__action__plan=plan_obj)
        cache.populate_persons(persons_queryset)
        cache.populate_organizations(
            Organization.objects.filter(
                Q(responsible_actions__action__plan=plan_obj) |
                Q(people__in=persons_queryset)
            )
        )
        if not is_authenticated(user):
            workflow_state = WorkflowStateEnum.PUBLISHED
        elif not user.can_access_public_site(plan=plan_obj):
            workflow_state = WorkflowStateEnum.PUBLISHED
        if workflow_state == WorkflowStateEnum.PUBLISHED:
            return qs
        else:
            return Query._resolve_plan_action_revisions(plan_obj, workflow_state, qs, cache=cache)

    @staticmethod
    def resolve_related_plan_actions(root, info, plan, first=None, category=None, order_by=None, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        plans = plan_obj.get_all_related_plans()
        qs = plans_actions_queryset(plans, category, first, order_by, info.context.user)
        return gql_optimizer.query(qs, info)

    @staticmethod
    def resolve_plan_categories(root, info, plan, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        qs = Category.objects.filter(type__plan=plan_obj)

        category_type = kwargs.get('category_type')
        if category_type is not None:
            qs = qs.filter(type__identifier=category_type)

        return gql_optimizer.query(qs, info)

    @staticmethod
    def resolve_action(
            root,
            info: GQLInfo,
            id: int | None = None,
            identifier: str | None = None,
            plan: str | None = None
    ) -> Action | None:

        workflow_state = info.context.watch_cache.query_workflow_state
        action = _resolve_published_action(id, identifier, plan, info)

        if action and not identifier:
            set_active_plan(info, action.plan)

        plan_obj = action.plan if action else None
        if plan_obj is None:
            return action

        user = info.context.user

        if not is_authenticated(user):
            workflow_state = WorkflowStateEnum.PUBLISHED
        elif not user.can_access_public_site(plan=plan_obj):
            workflow_state = WorkflowStateEnum.PUBLISHED
        if workflow_state != WorkflowStateEnum.PUBLISHED:
            if action is None:
                return None
            action = _resolve_action_revision(action, workflow_state)

        return action

    @staticmethod
    def resolve_category(root, info, plan, category_type, external_identifier):
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
