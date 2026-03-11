# ruff: noqa: ANN205
from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime
from itertools import chain
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Generic, Protocol, TypeVar
from urllib.parse import urlparse

import graphene
import strawberry
import strawberry as sb
import strawberry_django
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch, Q, prefetch_related_objects
from django.urls import reverse
from django.utils.translation import get_language, gettext, override
from graphene_django import DjangoObjectType
from graphene_django.converter import convert_django_field_with_choices
from graphql.error import GraphQLError
from wagtail.models import Revision, WorkflowState
from wagtail.rich_text import RichText

import graphene_django_optimizer as gql_optimizer
import sentry_sdk
from grapple.registry import registry as grapple_registry
from grapple.types.interfaces import get_page_interface

from kausal_common.datasets.models import Dataset
from kausal_common.graphene.grapple import make_grapple_streamfield
from kausal_common.graphene.registry import register_graphene_node
from kausal_common.strawberry.errors import PermissionDeniedError
from kausal_common.users import is_authenticated, user_or_none

from aplans import gql
from aplans.cache import SerializedDictWithRelatedObjectCache
from aplans.graphql_helpers import ModelAdminAdminButtonsMixin
from aplans.graphql_types import (
    DjangoNode,
    WorkflowStateDescription,
    WorkflowStateEnum,
    get_plan_from_context,
    is_plan_context_active,
    order_queryset,
    register_django_node,
    set_active_plan,
)
from aplans.utils import PlanRelatedModel, get_hostname_redirect_hostname, hyphenate_fi, public_fields

from actions.action_admin import ActionAdmin
from actions.action_status_summary import (
    ActionStatusSummaryIdentifier,
    ActionTimelinessIdentifier,
    Comparison,
    Sentiment as SentimentEnum,
)
from actions.models import (
    Action,
    ActionContactPerson,
    ActionImpact,
    ActionImplementationPhase,
    ActionLink,
    ActionResponsibleParty,
    ActionSchedule,
    ActionStatus,
    ActionStatusUpdate,
    ActionTask,
    AttributeCategoryChoice,
    AttributeChoice as AttributeChoiceModel,
    AttributeChoiceWithText,
    AttributeNumericValue,
    AttributeRichText,
    AttributeText,
    AttributeType,
    AttributeTypeChoiceOption,
    Category,
    CategoryLevel,
    CategoryType,
    CommonCategory,
    CommonCategoryType,
    ImpactGroup,
    ImpactGroupAction,
    MonitoringQualityPoint,
    Plan,
    PlanDomain,
    PlanFeatures,
    Pledge,
    PublicationStatus,
    Scenario,
)
from actions.models.action import ActionQuerySet
from actions.models.action_deps import ActionDependencyRelationship, ActionDependencyRole
from actions.models.attributes import ModelWithAttributes
from actions.models.category import IndicatorCategoryRelationshipType  # noqa: TC001
from orgs.models import Organization
from pages import schema as pages_schema
from pages.models import ActionListPage, AplansPage, CategoryPage, IndicatorListPage, PageChangeLogMessage
from people.models import Person
from search.backends import WatchSearchBackend, get_search_backend

from .models import (
    ActionChangeLogMessage,
    CategoryChangeLogMessage,
    IndicatorCategoryRelationship as IndicatorCategoryRelationshipModel,
    IndicatorChangeLogMessage,
    PledgeCommitment,
    PledgeUser,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from django.db import models
    from django.db.models import QuerySet
    from django_stubs_ext import StrOrPromise
    from strawberry import auto
    from wagtail.models import Page

    from aplans.cache import PlanSpecificCache
    from aplans.graphql_types import GQLInfo

    from actions.models.action import ActionQuerySet
    from actions.models.attributes import Attribute
    from actions.models.plan import PlanQuerySet
    from admin_site.models import BaseChangeLogMessage
    from indicators.models import ActionIndicator, IndicatorLevelQuerySet
    from indicators.schema import IndicatorNode
    from orgs.models import OrganizationQuerySet
    from users.models import User


logger = logging.getLogger(__name__)
PublicationStatusNode = graphene.Enum.from_enum(PublicationStatus)


class PlanDomainNode(DjangoNode[PlanDomain]):
    status = PublicationStatusNode(source='status')
    status_message = graphene.String(required=False, source='status_message')

    class Meta:
        model = PlanDomain
        fields = (
            'id',
            'hostname',
            'redirect_to_hostname',
            'base_path',
            'google_site_verification_tag',
            'matomo_analytics_url',
            'status',
            'status_message',
        )

    @staticmethod
    def resolve_redirect_to_hostname(root: PlanDomain, _info: GQLInfo) -> str | None:
        if root.redirect_to_hostname:
            return root.redirect_to_hostname

        redirect_hostnames = settings.REDIRECT_UI_HOSTNAMES
        if not redirect_hostnames:
            return None
        hostname = get_hostname_redirect_hostname(
            hostname=root.hostname,
            redirect_hostnames=redirect_hostnames,
            allowed_non_wildcard_hosts=set(),
            preserve_subdomain=True
        )
        if hostname:
            sentry_sdk.capture_message(f'Wildcard hostname UI redirect: {root.hostname} -> {hostname}', level='info')
        return hostname


class PlanFeaturesNode(DjangoNode[PlanFeatures]):
    public_contact_persons = graphene.Boolean(required=True)
    enable_moderation_workflow = graphene.Boolean(required=True)
    enable_community_engagement = graphene.Boolean(required=True)

    class Meta:
        model = PlanFeatures
        fields = public_fields(PlanFeatures)

    @staticmethod
    def resolve_public_contact_persons(root: PlanFeatures, _info: GQLInfo) -> bool:
        return root.public_contact_persons

    @staticmethod
    def resolve_enable_moderation_workflow(root: PlanFeatures, _info: GQLInfo) -> bool:
        return root.enable_moderation_workflow

    @staticmethod
    def resolve_enable_community_engagement(root: PlanFeatures, _info: GQLInfo) -> bool:
        return root.enable_community_engagement


def get_action_list_page_node():
    from grapple.registry import registry

    from pages.models import ActionListPage

    return registry.pages[ActionListPage]


def get_indicator_list_page_node():
    from grapple.registry import registry

    from pages.models import IndicatorListPage

    return registry.pages[IndicatorListPage]


T = TypeVar('T', bound=Plan)


class PlanInterface(graphene.Interface[T], Generic[T]):
    primary_language = graphene.String(required=True)
    published_at = graphene.DateTime()
    domain = graphene.Field(PlanDomainNode, hostname=graphene.String(required=False))
    domains = graphene.List(PlanDomainNode, hostname=graphene.String(required=False))
    status_message = graphene.String()
    login_enabled = graphene.Boolean()

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='domains',
    )
    def resolve_domain(root: Plan, info, hostname=None) -> PlanDomain | None:
        context_hostname = getattr(info.context, '_plan_hostname', None)
        if not hostname:
            hostname = context_hostname
        if not hostname:
            return None
        explicit_domains = root.domains.filter(plan=root, hostname=hostname).first()
        if explicit_domains:
            return explicit_domains

        implicit_domain = PlanDomain(
            plan=root,
            hostname=hostname,
            redirect_to_hostname=None,
            base_path='',
            redirect_aliases=[],
        )
        return implicit_domain

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('features',),
        only=('features__expose_unpublished_plan_only_to_authenticated_user',),
    )
    def resolve_login_enabled(root: Plan, _info: GQLInfo) -> bool:
        return root.features.expose_unpublished_plan_only_to_authenticated_user

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='domains',
    )
    def resolve_domains(root: Plan, info, hostname=None) -> None | QuerySet[PlanDomain, PlanDomain]:
        context_hostname = getattr(info.context, '_plan_hostname', None)
        if not hostname:
            hostname = context_hostname
            if not hostname:
                return None
        return root.domains.filter(plan=root, hostname=hostname)

    @classmethod
    def resolve_type(cls, instance: Plan, info: GQLInfo) -> type[RestrictedPlanNode | PlanNode]:
        context_hostname = getattr(info.context, '_plan_hostname', None)
        if context_hostname is None:
            return RestrictedPlanNode
        domains = instance.domains.filter(plan=instance, hostname=context_hostname)
        first_domain = domains.first()

        if instance.features.expose_unpublished_plan_only_to_authenticated_user is False:
            if first_domain is None or first_domain.status == PublicationStatus.PUBLISHED:
                return PlanNode
            return RestrictedPlanNode

        if first_domain:
            override = first_domain.publication_status_override
            if override is not None:
                if override == PublicationStatus.PUBLISHED:
                    return PlanNode
                if override == PublicationStatus.UNPUBLISHED:
                    return RestrictedPlanNode
        if instance.is_visible_for_user(info.context.user):
            return PlanNode
        return RestrictedPlanNode

    @staticmethod
    def resolve_status_message(root: Plan, info: GQLInfo, hostname=None) -> str | None:
        context_hostname = getattr(info.context, '_plan_hostname', None)
        if not hostname:
            hostname = context_hostname
            if not hostname:
                return None
        domain = root.domains.filter(plan=root, hostname=hostname).first()
        if domain is not None:
            return domain.status_message
        if root.is_live():
            return None
        with override(root.primary_language):
            return gettext('The site is not public at this time.')


@register_graphene_node
class RestrictedPlanNode(DjangoObjectType[Plan]):
    class Meta:
        interfaces = (PlanInterface,)
        model = Plan
        fields = ('primary_language', 'published_at', 'domain', 'domains')


class PlanNode(DjangoNode[Plan]):
    id = graphene.ID(source='identifier', required=True)
    last_action_identifier = graphene.ID()
    serve_file_base_url = graphene.String(required=True)
    pages = graphene.List(graphene.NonNull(get_page_interface))
    action_list_page = graphene.Field(get_action_list_page_node)
    indicator_list_page = graphene.Field(get_indicator_list_page_node)
    category_type = graphene.Field('actions.schema.CategoryTypeNode', id=graphene.ID(required=True))
    category_types = graphene.List(
        graphene.NonNull('actions.schema.CategoryTypeNode'),
        required=True,
        usable_for_indicators=graphene.Boolean(),
        usable_for_actions=graphene.Boolean(),
    )
    actions = graphene.List(
        graphene.NonNull('actions.schema.ActionNode'),
        identifier=graphene.ID(),
        id=graphene.ID(),
        only_mine=graphene.Boolean(default_value=False),
        responsible_organization=graphene.ID(required=False),
        first=graphene.Int(required=False),
        restrict_to_publicly_visible=graphene.Boolean(default_value=True),
        required=True,
    )
    action_attribute_types = graphene.List(
        graphene.NonNull('actions.schema.AttributeTypeNode', required=True),
        required=True,
    )
    impact_groups = graphene.List(graphene.NonNull('actions.schema.ImpactGroupNode'), first=graphene.Int(), required=True)
    image = graphene.Field('images.schema.ImageNode', required=False)
    indicator_levels = graphene.List(
        graphene.NonNull('indicators.schema.IndicatorLevelNode'),
        required=True,
    )

    primary_orgs = graphene.List(graphene.NonNull('orgs.schema.OrganizationNode'), required=True)

    admin_url = graphene.String(required=False)
    view_url = graphene.String(client_url=graphene.String(required=False))
    action_report_export_view_url = graphene.String(required=False)

    main_menu = pages_schema.MainMenuNode.create_plan_menu_field()
    footer = pages_schema.FooterNode.create_plan_menu_field()
    additional_links = pages_schema.AdditionalLinksNode.create_plan_menu_field()

    # FIXME: Legacy attributes, remove later
    hide_action_identifiers = graphene.Boolean(required=True)
    hide_action_official_name = graphene.Boolean(required=True)
    hide_action_lead_paragraph = graphene.Boolean(required=True)

    features = graphene.Field(PlanFeaturesNode, required=True)
    general_content = graphene.Field('aplans.schema.SiteGeneralContentNode', required=True)
    all_related_plans = graphene.List(graphene.NonNull('actions.schema.PlanNode'), required=True)

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
        graphene.NonNull('actions.schema.ActionStatusSummaryNode'),
        required=True,
    )
    action_timeliness_classes = graphene.List(
        graphene.NonNull('actions.schema.ActionTimelinessNode'),
        required=True,
    )

    has_indicator_relationships = graphene.Boolean()

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='indicator_levels',
    )
    def resolve_indicator_levels(root: Plan, info: GQLInfo) -> IndicatorLevelQuerySet:
        qs = root.indicator_levels.get_queryset()
        if not root.is_visible_for_user(info.context.user):
            return qs.none()
        return qs.visible_for_user(info.context.user)

    @staticmethod
    def resolve_action_status_summaries(root: Plan, info: GQLInfo):
        return [a.get_data({'plan': root, 'cache': info.context.cache}) for a in ActionStatusSummaryIdentifier]

    @staticmethod
    def resolve_action_timeliness_classes(root: Plan, info: GQLInfo):
        return [a.get_data({'plan': root, 'cache': info.context.cache}) for a in ActionTimelinessIdentifier]

    @staticmethod
    def resolve_last_action_identifier(root: Plan, _info: GQLInfo):
        return root.get_last_action_identifier()

    @staticmethod
    def resolve_category_type(root: Plan, info: GQLInfo, id: str):
        if not root.is_visible_for_user(info.context.user):
            return None
        return root.category_types.get(id=id)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='category_types',
    )
    def resolve_category_types(
        root: Plan, info: GQLInfo, usable_for_indicators: bool | None = None, usable_for_actions: bool | None = None
    ):
        if not root.is_visible_for_user(info.context.user):
            return root.category_types.none()
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
    def resolve_impact_groups(root: Plan, _info: GQLInfo, first: int | None = None):
        qs = root.impact_groups.all()
        if first is not None:
            qs = qs[0:first]
        return qs.order_by('pk')

    @staticmethod
    def resolve_serve_file_base_url(_root: Plan, info: GQLInfo):
        request = info.context
        return request.build_absolute_uri('/').rstrip('/')

    @staticmethod
    def resolve_pages(root: Plan, _info: GQLInfo):
        root_page: Page | None = root.root_page
        if not root_page:
            return None
        return root_page.get_descendants(inclusive=True).live().public().type(AplansPage).specific()

    @staticmethod
    def resolve_action_list_page(root: Plan, info: GQLInfo):
        cache = info.context.cache.for_plan(root)
        for page in cache.visible_pages:
            if type(page) is ActionListPage:
                return page
        return None

    @staticmethod
    def resolve_indicator_list_page(root: Plan, info: GQLInfo) -> IndicatorListPage | None:
        cache = info.context.cache.for_plan(root)
        for page in cache.visible_pages:
            if type(page) is IndicatorListPage:
                return page
        return None

    @staticmethod
    def resolve_view_url(root: Plan, info: GQLInfo, client_url: str | None = None):
        if client_url:
            try:
                urlparse(client_url)
            except Exception:
                raise GraphQLError("clientUrl must be a valid URL") from None
        return root.get_view_url(client_url=client_url, active_locale=get_language(), request=info.context)

    @staticmethod
    def resolve_admin_url(root: Plan, info: GQLInfo):
        if not root.is_visible_for_user(info.context.user):
            return None
        client_plan = root.clients.first()
        if client_plan is None:
            return None
        return client_plan.client.get_admin_url()

    @staticmethod
    def resolve_action_report_export_view_url(root: Plan, info: GQLInfo) -> str:
        return info.context.build_absolute_uri(reverse('action-report-export', kwargs={'plan_identifier': root.identifier}))

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
        first: int | None = None,
    ):
        user = info.context.user
        qs = root.actions.get_queryset()
        qs = qs.visible_for_user(user).filter(plan=root)
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
    def resolve_action_attribute_types(root: Plan, info: GQLInfo):
        user = info.context.user
        attribute_types = root.action_attribute_types.order_by('pk')
        return [at for at in attribute_types if at.is_instance_visible_for(user, root, None)]

    @staticmethod
    def resolve_primary_orgs(root: Plan, _info: GQLInfo) -> OrganizationQuerySet:
        qs = Action.objects.filter(plan=root).values_list('primary_org').distinct()
        return Organization.objects.qs.filter(id__in=qs)

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('features',),
    )
    def resolve_hide_action_identifiers(root: Plan, _info: GQLInfo):
        return not root.features.show_action_identifiers

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('features',),
    )
    def resolve_hide_action_lead_paragraph(root: Plan, _info: GQLInfo):
        return not root.features.has_action_lead_paragraph

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('features',),
    )
    def resolve_hide_action_official_name(root: Plan, _info: GQLInfo):
        return not root.features.has_action_official_name

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('parent',),
    )
    def resolve_all_related_plans(root: Plan, info: GQLInfo) -> PlanQuerySet:
        return root.get_all_related_plans().visible_for_user(info.context.user)

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('image',),
        only=('image',),
    )
    def resolve_image(root: Plan, _info: GQLInfo):
        return root.image

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('primary_action_classification',),
        only=('primary_action_classification',),
    )
    def resolve_primary_action_classification(root: Plan, _info: GQLInfo):
        return root.primary_action_classification

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('secondary_action_classification',),
        only=('secondary_action_classification',),
    )
    def resolve_secondary_action_classification(root: Plan, _info: GQLInfo):
        return root.secondary_action_classification

    @staticmethod
    def resolve_action_update_target_interval(root: Plan, _info: GQLInfo):
        return root.action_update_target_interval

    @staticmethod
    def resolve_action_update_acceptable_interval(root: Plan, _info: GQLInfo):
        return root.action_update_acceptable_interval

    @staticmethod
    def resolve_superseding_plans(root: Plan, info: GQLInfo, recursive: bool = False):
        return root.get_superseding_plans(recursive, info.context.user)

    @staticmethod
    def resolve_superseded_plans(root: Plan, info: GQLInfo, recursive: bool = False):
        return root.get_superseded_plans(recursive).visible_for_user(info.context.user)

    @staticmethod
    def resolve_superseded_by(root: Plan, info: GQLInfo) -> Plan | None:
        superseded_by = root.superseded_by
        return superseded_by.get_if_visible(info.context.user) if superseded_by else None

    @staticmethod
    def resolve_has_indicator_relationships(root: Plan, info: GQLInfo):
        return root.has_indicator_relationships(info.context.user)

    # Community engagement: Pledges
    pledge = graphene.Field(
        'actions.schema.PledgeNode',
        id=graphene.ID(),
        slug=graphene.String(),
    )
    pledges = graphene.List(graphene.NonNull('actions.schema.PledgeNode'))

    @staticmethod
    def resolve_pledge(root: Plan, info: GQLInfo, id: str | None = None, slug: str | None = None):
        if not root.features.enable_community_engagement:
            return None

        qs = Pledge.objects.filter(plan=root)

        if id:
            return qs.filter(id=id).first()
        if slug:
            return qs.filter(slug=slug).first()
        return None

    @staticmethod
    def resolve_pledges(root: Plan, info: GQLInfo):
        if not root.features.enable_community_engagement:
            return None

        return Pledge.objects.filter(plan=root).order_by('order')
    class Meta:
        model = Plan
        interfaces = (PlanInterface,)
        fields = public_fields(Plan)


type AttributeObject = (
    AttributeCategoryChoice
    | AttributeChoiceModel
    | AttributeChoiceWithText
    | AttributeText
    | AttributeRichText
    | AttributeNumericValue
)


class AttributeInterface(graphene.Interface[AttributeObject]):
    id = graphene.ID(required=True)
    type_ = graphene.Field('actions.schema.AttributeTypeNode', name='type', required=True)
    key = graphene.String(required=True)
    key_identifier = graphene.String(required=True)

    @staticmethod
    def resolve_key(root: AttributeObject, _info: GQLInfo):
        return root.type.name

    @staticmethod
    def resolve_key_identifier(root: AttributeObject, _info: GQLInfo):
        return root.type.identifier

    @staticmethod
    def resolve_id(root: AttributeObject, _info: GQLInfo):
        return getattr(root, 'pk', None) or f'unpublished-{uuid.uuid4()}'

    @staticmethod
    def resolve_type_(root: AttributeObject, _info: GQLInfo) -> AttributeType:
        return root.type

    @classmethod
    def resolve_type(cls, instance: AttributeObject, _info: GQLInfo) -> type[graphene.ObjectType[Any]] | None:
        if isinstance(instance, AttributeText):
            return AttributeTextNode
        if isinstance(instance, AttributeRichText):
            return AttributeRichTextNode
        if isinstance(instance, (AttributeChoiceModel, AttributeChoiceWithText)):
            return AttributeChoice
        if isinstance(instance, AttributeNumericValue):
            return AttributeNumericValueNode
        if isinstance(instance, AttributeCategoryChoice):
            return AttributeCategoryChoiceNode
        return None


@register_graphene_node
class AttributeChoice(graphene.ObjectType[AttributeChoiceModel | AttributeChoiceWithText]):
    id = graphene.ID(required=True)
    choice = graphene.Field(
        'actions.schema.AttributeTypeChoiceOptionNode',
        required=False,
    )
    text = graphene.String(required=False)

    @staticmethod
    def resolve_id(root: AttributeChoiceModel | AttributeChoiceWithText, _info: GQLInfo):
        if isinstance(root, AttributeChoiceModel):
            prefix = 'C'
        else:
            prefix = 'CT'
        return f'{prefix}{root.pk}'

    def resolve_text(self, _info: GQLInfo):
        return getattr(self, 'text_i18n', None)

    class Meta:
        interfaces = (AttributeInterface,)


@register_django_node
class AttributeTextNode(DjangoNode[AttributeText]):
    value = graphene.String(required=True)

    @staticmethod
    def resolve_value(root: AttributeText, _info: GQLInfo):
        return root.text_i18n

    class Meta:
        model = AttributeText
        interfaces = (AttributeInterface,)
        # We expose `value` instead of `text`
        fields = public_fields(AttributeText, remove_fields=['text'])


@register_django_node
class AttributeRichTextNode(DjangoNode[AttributeRichText]):
    value = graphene.String(required=True)

    @staticmethod
    def resolve_value(root: AttributeRichText, _info: GQLInfo):
        return RichText(root.text_i18n)

    class Meta:
        model = AttributeRichText
        interfaces = (AttributeInterface,)
        # We expose `value` instead of `text`
        fields = public_fields(AttributeRichText, remove_fields=['text'])


@register_django_node
class AttributeCategoryChoiceNode(DjangoNode[AttributeCategoryChoice]):
    class Meta:
        model = AttributeCategoryChoice
        interfaces = (AttributeInterface,)
        fields = public_fields(AttributeCategoryChoice)


@register_django_node
class AttributeNumericValueNode(DjangoNode[AttributeNumericValue]):
    class Meta:
        model = AttributeNumericValue
        interfaces = (AttributeInterface,)
        fields = public_fields(AttributeNumericValue)


@register_django_node
class CategoryLevelNode(DjangoNode[CategoryLevel]):
    class Meta:
        model = CategoryLevel
        fields = public_fields(CategoryLevel)


def django_choices_to_graphene(field: models.Field[Any, Any]):
    from graphene_django.registry import get_global_registry
    registry = get_global_registry()
    graphene_type = convert_django_field_with_choices(field, registry=registry, convert_choices_to_enum=True)
    return graphene_type._type._of_type


AttributeTypeFormat = django_choices_to_graphene(AttributeType._meta.get_field('format'))  # pyright: ignore[reportArgumentType]


@register_django_node
class AttributeTypeNode(DjangoNode[AttributeType]):
    format = graphene.Field(AttributeTypeFormat, required=True)
    class Meta:
        model = AttributeType
        fields = public_fields(AttributeType)


@register_django_node
class AttributeTypeChoiceOptionNode(DjangoNode[AttributeTypeChoiceOption]):
    class Meta:
        model = AttributeTypeChoiceOption
        fields = public_fields(AttributeTypeChoiceOption)


class HasLeadParagraph(Protocol):
    lead_paragraph: str | None


# TODO: Remove this when production UI is updated
class ResolveShortDescriptionFromLeadParagraphShim:
    short_description = graphene.String()

    @staticmethod
    def resolve_short_description(root: HasLeadParagraph, _info: GQLInfo) -> str | None:
        return root.lead_paragraph


CategoryTypeSelectWidget = django_choices_to_graphene(CategoryType._meta.get_field('select_widget'))  # pyright: ignore[reportArgumentType]


@register_django_node
class CategoryTypeNode(ResolveShortDescriptionFromLeadParagraphShim, DjangoNode[CategoryType]):
    attribute_types = graphene.List(graphene.NonNull(AttributeTypeNode), required=True)
    selection_type = graphene.NonNull(
        CategoryTypeSelectWidget, description=str(CategoryType._meta.get_field('select_widget').help_text)  # pyright: ignore[reportAttributeAccessIssue]
    )
    categories = graphene.List(
        graphene.NonNull('actions.schema.CategoryNode'),
        only_root=graphene.Boolean(default_value=False),
        only_with_actions=graphene.Boolean(default_value=False),
        required=True,
    )

    class Meta:
        model = CategoryType
        fields = public_fields(CategoryType, remove_fields=['select_widget'])

    @staticmethod
    def resolve_attribute_types(root: CategoryType, _info: GQLInfo):
        return root.attribute_types.order_by('pk')

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='select_widget',
    )
    def resolve_selection_type(root: CategoryType, _info: GQLInfo):
        return root.select_widget

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='categories',
    )
    def resolve_categories(root: CategoryType, _info: GQLInfo, only_root: bool, only_with_actions: bool):
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

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('plan',),
    )
    def resolve_plan(root: CategoryType, info: GQLInfo) -> Plan | None:
        return root.plan.get_if_visible(info.context.user)


@register_django_node
class CommonCategoryTypeNode(ResolveShortDescriptionFromLeadParagraphShim, DjangoNode[CommonCategoryType]):
    class Meta:
        model = CommonCategoryType
        fields = public_fields(CommonCategoryType)


def get_translated_category_page(_info, **_kwargs) -> Prefetch:  # pyright: ignore[reportMissingTypeArgument]
    qs = CategoryPage.objects.filter(locale__language_code__iexact=get_language())
    return Prefetch('category_pages', to_attr='category_pages_locale', queryset=qs)


def prefetch_workflow_states(_info, **_kwargs) -> Prefetch:  # pyright: ignore[reportMissingTypeArgument]
    workflow_states = (
        WorkflowState._default_manager.get_queryset()
        .active()
        .select_related(  # pyright: ignore[reportAttributeAccessIssue]
            'current_task_state__task',
        )
    )
    return Prefetch(
        '_workflow_states',
        queryset=workflow_states,
        to_attr='_current_workflow_states',
    )


class AttributesMixin:
    attributes = graphene.List(graphene.NonNull(AttributeInterface), id=graphene.ID(required=False), required=True)

    @staticmethod
    @gql_optimizer.resolver_hints(
        prefetch_related=[
            *chain(*[(f'{rel}__type', f'{rel}__content_object') for rel in ModelWithAttributes.ATTRIBUTE_RELATIONS]),
            *['choice_attributes__choice__type', 'choice_with_text_attributes__choice__type'],
        ],
    )
    def resolve_attributes(root: ModelWithAttributes, info: GQLInfo, id: str | None = None):
        request = info.context

        plan_identifier = info.variable_values.get('plan')
        if not is_plan_context_active(info):
            # All current ModelWithAttributes subclasses also inherit PlanRelatedModel, but Python can't express that
            # intersection type in the method signature yet.
            assert isinstance(root, PlanRelatedModel)
            obj_plan = root.get_plans()[0]
            cache = info.context.cache.for_plan(obj_plan)
            plan = cache.plan
        else:
            plan = get_plan_from_context(info, plan_identifier)

        def filter_attrs(attributes: Iterable[Attribute]) -> list[Attribute]:
            result = []
            for attribute in attributes:
                id_mismatch = id is not None and attribute.type.identifier != id
                if not id_mismatch and attribute.is_visible_for_user(request.user, plan):
                    result.append(attribute)
            return result

        attributes: list[Attribute] = []
        if root.draft_attributes:
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


def indicators_schema():
    from indicators import schema

    return schema


@strawberry_django.type(IndicatorCategoryRelationshipModel, description="A relationship between an indicator and a category")
class IndicatorCategoryRelationship:
    id: auto
    indicator: Annotated[IndicatorNode, strawberry.lazy('indicators.schema')]
    type: IndicatorCategoryRelationshipType


@register_django_node
class CategoryNode(ResolveShortDescriptionFromLeadParagraphShim, AttributesMixin, DjangoNode[Category]):
    image = graphene.Field('images.schema.ImageNode')
    level = graphene.Field(CategoryLevelNode)
    actions = graphene.List(graphene.NonNull('actions.schema.ActionNode'))
    icon_image = graphene.Field('images.schema.ImageNode')
    icon_svg_url = graphene.String()
    category_page = graphene.Field(grapple_registry.pages[CategoryPage])
    datasets = graphene.List(graphene.NonNull('datasets.schema.DatasetNode'), required=True)
    indicator_relationships = graphene.List(graphene.NonNull(IndicatorCategoryRelationship), required=True)
    change_log_message = graphene.Field('actions.schema.ChangeLogMessageInterface')

    @staticmethod
    def _resolve_field_with_fallback_to_common(root: Category, field_name: str):
        value = getattr(root, field_name)
        if value or root.common is None:
            return value
        return getattr(root.common, field_name)

    @staticmethod
    def resolve_image(root: Category, _info: GQLInfo):
        return CategoryNode._resolve_field_with_fallback_to_common(root, 'image')

    @staticmethod
    def resolve_level(root: Category, _info: GQLInfo):
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
    def resolve_actions(root: Category, info: GQLInfo) -> ActionQuerySet:
        return root.actions.get_queryset().visible_for_user(info.context.user)

    @staticmethod
    def resolve_indicator_relationships(root: Category, info: GQLInfo) -> list[IndicatorCategoryRelationshipModel]:
        return list(root.indicator_relationships.all())

    @staticmethod
    @gql_optimizer.resolver_hints(
        prefetch_related=get_translated_category_page,
    )
    def resolve_category_page(root: Category, _info: GQLInfo):
        # If we have prefetched the page in the right locale, use that
        if hasattr(root, 'category_pages_locale'):
            pages = root.category_pages_locale  # pyright: ignore
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
        only=('common',),
    )
    def resolve_icon_image(root: Category, _info: GQLInfo):
        icon = root.get_icon(get_language())
        if icon:
            return icon.image
        return None

    @staticmethod
    @gql_optimizer.resolver_hints(
        prefetch_related=('icons',),
        select_related=('common',),
        only=('common',),
    )
    def resolve_icon_svg_url(root: Category, info: GQLInfo):
        icon = root.get_icon(get_language())
        if icon and icon.image.filename.endswith('.svg'):
            return info.context.build_absolute_uri(icon.image.file.url)
        return None

    @staticmethod
    def resolve_help_text(root: Category, _info: GQLInfo):
        return CategoryNode._resolve_field_with_fallback_to_common(root, 'help_text_i18n')

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='lead_paragraph',
        select_related=('type__plan'),
        only=('lead_paragraph', 'i18n', 'type__plan__primary_language', 'type__plan__primary_language_lowercase'),
    )
    def resolve_lead_paragraph(root: Category, _info: GQLInfo):
        return CategoryNode._resolve_field_with_fallback_to_common(root, 'lead_paragraph_i18n')

    @staticmethod
    def resolve_datasets(root: Category, _info: GQLInfo):
        category_content_type = ContentType.objects.get_for_model(Category)
        return Dataset.objects.filter(
            scope_content_type=category_content_type,
            scope_id=root.id,
        )

    @staticmethod
    def resolve_change_log_message(root: Category, info: GQLInfo):
        return root.get_public_change_log_message()

    class Meta:
        model = Category
        fields = public_fields(Category, add_fields=['level', 'icon_image', 'icon_svg_url'])


@register_django_node
class CommonCategoryNode(ResolveShortDescriptionFromLeadParagraphShim, DjangoNode[CommonCategory]):
    icon_image = graphene.Field('images.schema.ImageNode')
    icon_svg_url = graphene.String()
    category_instances = graphene.List(graphene.NonNull(CategoryNode), required=True)

    @staticmethod
    def resolve_icon_image(root: CommonCategory, _info: GQLInfo):
        icon = root.get_icon(get_language())
        if icon:
            return icon.image
        return None

    @staticmethod
    def resolve_icon_svg_url(root, info: GQLInfo):
        icon = root.get_icon(get_language())
        if icon and icon.image.filename.endswith('.svg'):
            return info.context.build_absolute_uri(icon.image.file.url)
        return None

    @staticmethod
    def resolve_category_instances(root: CommonCategory, info: GQLInfo):
        return root.category_instances.filter(
            type__plan=Plan.objects.get_queryset().live().visible_for_user(info.context.user)
        )

    class Meta:
        model = CommonCategory
        fields = public_fields(CommonCategory)


def _get_pledge_body_field() -> graphene.Field:
    """
    Create a typed GraphQL field for Pledge.body StreamField.

    This uses grapple's make_grapple_streamfield to create a proper union type
    for the body field's blocks (RichTextBlock, QuestionAnswerBlock, LargeImageBlock)
    instead of returning generic stream data.
    """
    # TODO: We should probably make that generic and put it next to make_grapple_streamfield().
    # Get the grapple field resolver
    grapple_field_resolver = make_grapple_streamfield(lambda: Pledge, 'body')
    result = grapple_field_resolver()

    # Handle the result - can be GraphQLField or tuple of (GraphQLField, wrapper_callable)
    if isinstance(result, tuple):
        graphql_field, wrapper_callable = result
        field_type = graphql_field.field_type
        return wrapper_callable(field_type)
    # Single block type case - return as graphene.Field directly
    # Note: field_type is already wrapped with NonNull if required=True was passed to GraphQLField
    graphql_field = result
    return graphene.Field(graphql_field.field_type)


@register_django_node
class PledgeNode(AttributesMixin, DjangoNode[Pledge]):
    actions = graphene.List(graphene.NonNull('actions.schema.ActionNode'))
    image = graphene.Field('images.schema.ImageNode')
    commitment_count = graphene.Int(required=True, description="Number of commitments to this pledge")

    # Use grapple's streamfield handling for typed body blocks
    body = _get_pledge_body_field()

    class Meta:
        model = Pledge
        fields = [
            'id',
            'uuid',
            'name',
            'slug',
            'description',
            'image',
            # 'body' is defined as a class attribute above, not auto-converted
            'resident_count',
            'impact_statement',
            'local_equivalency',
            'actions',
            'plan',
            'order',
        ]

    @staticmethod
    def resolve_actions(root: Pledge, info: GQLInfo):
        return root.actions.get_queryset().visible_for_user(info.context.user)

    @staticmethod
    def resolve_image(root: Pledge, _info: GQLInfo):
        return root.image

    @staticmethod
    def resolve_commitment_count(root: Pledge, _info: GQLInfo) -> int:
        return root.commitments.count()


class PledgeCommitmentNode(DjangoNode[PledgeCommitment]):
    pledge = graphene.Field(PledgeNode)

    class Meta:
        model = PledgeCommitment
        fields = [
            'id',
            'pledge',
            'created_at',
        ]

    @staticmethod
    def resolve_pledge(root: PledgeCommitment, info: GQLInfo) -> Pledge | None:
        pledge = root.pledge
        if not pledge.plan.features.enable_community_engagement:
            return None
        return pledge


class PledgeUserNode(DjangoNode[PledgeUser]):
    commitments = graphene.List(
        graphene.NonNull(PledgeCommitmentNode),
        plan=graphene.ID(description="Filter commitments by plan identifier"),
    )

    class Meta:
        model = PledgeUser
        fields = [
            'id',
            'uuid',
            'user_data',
            'created_at',
        ]

    @staticmethod
    def resolve_commitments(root: PledgeUser, info: GQLInfo, plan: str | None = None):
        qs = root.commitments.filter(
            pledge__plan__features__enable_community_engagement=True,
        ).select_related('pledge', 'pledge__plan', 'pledge__plan__features')
        if plan is not None:
            qs = qs.filter(pledge__plan__identifier=plan)
        return qs


class ScenarioNode(DjangoNode[Scenario]):
    class Meta:
        model = Scenario
        fields = public_fields(Scenario)


class ImpactGroupNode(DjangoNode[ImpactGroup]):
    class Meta:
        model = ImpactGroup
        fields = public_fields(ImpactGroup)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('plan'),
    )
    def resolve_plan(root: ImpactGroup, info: GQLInfo) -> Plan | None:
        return root.plan.get_if_visible(info.context.user)


class ImpactGroupActionNode(DjangoNode[ImpactGroupAction]):
    class Meta:
        model = ImpactGroupAction
        fields = public_fields(ImpactGroupAction)


class MonitoringQualityPointNode(DjangoNode[MonitoringQualityPoint]):
    name = graphene.String()
    description_yes = graphene.String()
    description_no = graphene.String()

    class Meta:
        model = MonitoringQualityPoint
        fields = public_fields(MonitoringQualityPoint)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('plan'),
    )
    def resolve_plan(root: MonitoringQualityPoint, info: GQLInfo) -> Plan | None:
        return root.plan.get_if_visible(info.context.user)


class ActionTaskNode(DjangoNode[ActionTask]):
    class Meta:
        model = ActionTask
        fields = public_fields(ActionTask)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='comment',
    )
    def resolve_comment(root: ActionTask, _info: GQLInfo):
        root.i18n  # Workaround to avoid i18n field being deferred in gql_optimizer  # noqa: B018
        comment = root.comment_i18n
        if comment is None:
            return None

        return RichText(comment)


ActionStatusSummaryIdentifierNode = graphene.Enum.from_enum(ActionStatusSummaryIdentifier)
ActionTimelinessIdentifierNode = graphene.Enum.from_enum(ActionTimelinessIdentifier)
Sentiment = graphene.Enum.from_enum(SentimentEnum)


@register_graphene_node
class ActionStatusSummaryNode(graphene.ObjectType[Any]):
    identifier = ActionStatusSummaryIdentifierNode(required=True)
    label = graphene.String(required=True)
    color = graphene.String(
        required=True,
        deprecation_reason='This field is an internal implementation detail; most often you should use action.color',
    )
    is_active = graphene.Boolean(required=True)
    is_completed = graphene.Boolean(required=True)
    sentiment = Sentiment(required=True)

    class Meta:
        name = 'ActionStatusSummary'


@register_graphene_node
class ActionTimelinessNode(graphene.ObjectType[Any]):
    identifier = ActionTimelinessIdentifierNode(required=True)
    label = graphene.String(required=True, deprecation_reason='Generate human-friendly labels in the UI.')
    color = graphene.String(required=True)
    sentiment = Sentiment(required=True)
    comparison = graphene.Enum.from_enum(Comparison)(required=True)
    days = graphene.Int(required=True)

    class Meta:
        name = 'ActionTimeliness'


@register_django_node
class ActionDependencyRoleNode(DjangoNode[ActionDependencyRole]):
    class Meta:
        model = ActionDependencyRole
        fields = ActionDependencyRole.public_fields


@register_django_node
class ActionDependencyRelationshipNode(DjangoNode[ActionDependencyRelationship]):
    class Meta:
        model = ActionDependencyRelationship
        fields = ActionDependencyRelationship.public_fields


def _get_visible_action(root, field_name: str, user: User | None) -> Action | None:
    action_id = getattr(root, f'{field_name}_id')
    if action_id is None:
        return None
    try:
        return Action.objects.get_queryset().visible_for_user(user).get(id=action_id)
    except Action.DoesNotExist:
        return None


def _get_visible_actions(root, field_name: str, user: User | None) -> QuerySet[Action]:
    actions = getattr(root, field_name)
    return actions.visible_for_user(user)


class RevisionNode(DjangoNode[Revision[Any]]):
    class Meta:
        model = Revision
        fields = ('created_at',)


class WorkflowStateInfoNode(DjangoNode[WorkflowState]):
    status_message = graphene.String(required=True)

    class Meta:
        model = WorkflowState
        fields = ('status',)

    @staticmethod
    def resolve_status_message(root: WorkflowState, _info: GQLInfo) -> str | None:
        status_choices = dict(WorkflowState.STATUS_CHOICES)
        msg = status_choices.get(root.status)
        if msg is None:
            return None
        return str(msg)


class WorkflowInfoNode(graphene.ObjectType[Any]):
    has_unpublished_changes = graphene.Boolean(default_value=False, required=True)
    latest_revision = graphene.Field('actions.schema.RevisionNode', required=False)
    current_workflow_state = graphene.Field(
        'actions.schema.WorkflowStateInfoNode',
        description=(
            "The internal Wagtail workflow state of the action. "
            "The current action data returned does not necessarily match this "
            "workflowstate."
        ),
        required=False,
    )
    matching_version = graphene.Field(
        WorkflowStateDescription,
        description=(
            "The actual version of the action returned "
            "when fulfilling this query, based on both the requested workflow directive value used when querying "
            "an action, and the available versions of the action itself."
        ),
    )

    @staticmethod
    def resolve_has_unpublished_changes(root: Action, _info: GQLInfo) -> bool:
        return root.has_unpublished_changes

    @staticmethod
    def resolve_latest_revision(root: Action, _info: GQLInfo) -> Revision[Action] | None:
        return root.get_latest_revision()

    @staticmethod
    def resolve_current_workflow_state(root: Action, _info: GQLInfo) -> WorkflowState | None:
        return root.current_workflow_state

    @staticmethod
    def resolve_matching_version(root: Action, _info: GQLInfo) -> Mapping[str, StrOrPromise | None]:
        def make_result(match: WorkflowStateEnum) -> Mapping[str, StrOrPromise | None]:
            return dict(
                id=match.name,
                description=WorkflowStateEnum(match).description,
            )

        return make_result(getattr(root, '_actual_workflow_state', WorkflowStateEnum.PUBLISHED))


class ChangeLogMessageInterface(graphene.Interface[T], Generic[T]):
    content = graphene.String()
    created_at = graphene.DateTime()
    updated_at = graphene.DateTime()
    created_by = graphene.Field('people.schema.PersonNode')

    @classmethod
    def resolve_type(cls, instance: BaseChangeLogMessage, _info: GQLInfo) -> type[graphene.ObjectType[Any]] | None:
        if isinstance(instance, ActionChangeLogMessage):
            return ActionChangeLogMessageNode
        if isinstance(instance, IndicatorChangeLogMessage):
            return IndicatorChangeLogMessageNode
        if isinstance(instance, CategoryChangeLogMessage):
            return CategoryChangeLogMessageNode
        # Import here to avoid circular dependency
        from pages.models import PageChangeLogMessage

        if isinstance(instance, PageChangeLogMessage):
            return PageChangeLogMessageNode
        return None

    @staticmethod
    def resolve_created_by(root: BaseChangeLogMessage, _info: GQLInfo) -> Person | None:
        if root.created_by is None:
            return None
        return root.created_by.person


@register_django_node
class ActionChangeLogMessageNode(DjangoNode[ActionChangeLogMessage]):
    class Meta:
        model = ActionChangeLogMessage
        fields = ActionChangeLogMessage.public_fields
        interfaces = (ChangeLogMessageInterface,)


@register_django_node
class IndicatorChangeLogMessageNode(DjangoNode[IndicatorChangeLogMessage]):
    class Meta:
        model = IndicatorChangeLogMessage
        fields = IndicatorChangeLogMessage.public_fields
        interfaces = (ChangeLogMessageInterface,)


@register_django_node
class CategoryChangeLogMessageNode(DjangoNode[CategoryChangeLogMessage]):
    class Meta:
        model = CategoryChangeLogMessage
        fields = CategoryChangeLogMessage.public_fields
        interfaces = (ChangeLogMessageInterface,)


@register_django_node
class PageChangeLogMessageNode(DjangoNode[PageChangeLogMessage]):
    class Meta:
        from pages.models import PageChangeLogMessage

        model = PageChangeLogMessage
        fields = PageChangeLogMessage.public_fields
        interfaces = (ChangeLogMessageInterface,)


@register_django_node
class ActionNode(ModelAdminAdminButtonsMixin, AttributesMixin, DjangoNode[Action]):
    ORDERABLE_FIELDS: ClassVar[Sequence[str]] = ['updated_at', 'identifier']

    name = graphene.String(hyphenated=graphene.Boolean(), required=True)
    categories = graphene.List(graphene.NonNull(CategoryNode), category_type=graphene.ID(), required=True)
    contact_persons = graphene.List(
        graphene.NonNull('actions.schema.ActionContactPersonNode'),
        required=True,
        show_all_contact_persons=graphene.Boolean(default_value=False),
        description=(
            "Contact persons for this action. Results may be empty or redacted for "
            "unauthenticated requests depending on the plan's public contact person settings "
            "(see PlanFeatures.publicContactPersons)."
        ),
    )
    next_action = graphene.Field('actions.schema.ActionNode')
    previous_action = graphene.Field('actions.schema.ActionNode')
    image = graphene.Field('images.schema.ImageNode')
    view_url = graphene.String(client_url=graphene.String(required=False), required=True)
    edit_url = graphene.String()
    similar_actions = graphene.List('actions.schema.ActionNode')
    status_summary = graphene.Field('actions.schema.ActionStatusSummaryNode', required=True)
    timeliness = graphene.Field('actions.schema.ActionTimelinessNode', required=True)
    color = graphene.String(required=False)
    has_dependency_relationships = graphene.Boolean()
    all_dependency_relationships = graphene.List(
        graphene.NonNull('actions.schema.ActionDependencyRelationshipNode'),
        required=True,
    )
    workflow_status = graphene.Field('actions.schema.WorkflowInfoNode')
    change_log_message = graphene.Field(ChangeLogMessageInterface)

    indicators_count = graphene.Int()
    has_indicators_with_goals = graphene.Boolean()

    datasets = graphene.List(graphene.NonNull('datasets.schema.DatasetNode'), required=True)

    class Meta:
        model = Action
        fields = Action.public_fields

    @staticmethod
    def resolve_change_log_message(root: Action, info: GQLInfo):
        return root.get_public_change_log_message()

    @staticmethod
    def resolve_merged_with(root: Action, info: GQLInfo):
        return _get_visible_action(root, 'merged_with', user_or_none(info.context.user))

    @staticmethod
    def resolve_superseded_by(root: Action, info: GQLInfo):
        return _get_visible_action(root, 'superseded_by', user_or_none(info.context.user))

    @staticmethod
    def resolve_copy_of(root: Action, info: GQLInfo) -> Action | None:
        return _get_visible_action(root, 'copy_of', user_or_none(info.context.user))

    @staticmethod
    def resolve_merged_actions(root: Action, info: GQLInfo):
        return _get_visible_actions(root, 'merged_actions', user_or_none(info.context.user))

    @staticmethod
    def resolve_superseded_actions(root: Action, info: GQLInfo):
        return _get_visible_actions(root, 'superseded_actions', user_or_none(info.context.user))

    @staticmethod
    def resolve_copies(root: Action, info: GQLInfo) -> QuerySet[Action]:
        return _get_visible_actions(root, 'copies', user_or_none(info.context.user))

    @staticmethod
    def resolve_related_actions(root: Action, info: GQLInfo):
        return _get_visible_actions(root, 'related_actions', user_or_none(info.context.user))

    @staticmethod
    def resolve_next_action(root: Action, info: GQLInfo):
        return root.get_next_action(user_or_none(info.context.user))

    @staticmethod
    def resolve_previous_action(root: Action, info: GQLInfo):
        return root.get_previous_action(user_or_none(info.context.user))

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('plan'),
    )
    def resolve_plan(root: Action, info: GQLInfo) -> Plan | None:
        return root.plan.get_if_visible(user_or_none(info.context.user))

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='related_indicators',
    )
    def resolve_related_indicators(root: Action, info: GQLInfo) -> Iterable[ActionIndicator]:
        plan = root.plan
        indicators = root.get_visible_related_indicators(user_or_none(info.context.user))
        #  When accessing as Action draft revision, indicators are a FakeQuerySet without the
        #  features of ActionIndicatorQuerySet
        if hasattr(indicators, 'order_by_setting'):
            return indicators.order_by_setting(plan)
        return indicators

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='name',
        select_related=('plan'),
        only=('name', 'i18n', 'plan__primary_language', 'plan__primary_language_lowercase'),
    )
    def resolve_name(root: Action, _info: GQLInfo, hyphenated: bool = False):
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
    def resolve_description(root: Action, _info: GQLInfo):
        description = root.description_i18n
        if description is None:
            return None
        return RichText(description)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('lead_paragraph', 'i18n', 'plan__primary_language', 'plan__primary_language_lowercase'),
    )
    def resolve_lead_paragraph(root: Action, _info: GQLInfo):
        return root.lead_paragraph_i18n

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('plan', 'identifier'),
    )
    def resolve_view_url(root: Action, info: GQLInfo, client_url: str | None = None):
        return root.get_view_url(client_url=client_url, request=info.context)

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('status', 'implementation_phase'),
        only=(
            'plan',
            'merged_with',
            'status__color',
            'status__identifier',
            'implementation_phase__color',
            'implementation_phase__identifier',
        ),
    )
    def resolve_color(root: Action, info: GQLInfo):
        return root.get_color(cache=info.context.cache)

    @staticmethod
    def resolve_edit_url(root: Action, info: GQLInfo):
        if not root.plan.is_visible_for_user(info.context.user):
            return None
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
    def resolve_categories(root: Action, _info: GQLInfo, category_type: str | None = None):
        qs = root.categories.all()
        if category_type is not None:
            # Filter the materialized queryset instead of `qs.filter()` because a bug in modelcluster would load to
            # wrong results.
            # https://github.com/wagtail/django-modelcluster/issues/170
            # The categories and their types should all be cached.
            return [cat for cat in qs if cat.type.identifier == category_type]
        return qs

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='contact_persons',
        prefetch_related='contact_persons__person',
    )
    def resolve_contact_persons(root: Action, info: GQLInfo, show_all_contact_persons: bool = False):
        if not is_plan_context_active(info):
            plan = root.plan
        else:
            plan = get_plan_from_context(info)
        user = info.context.user
        if not plan.is_visible_for_user(user):
            return []
        cache = info.context.cache.for_plan(plan)
        return root.get_redacted_contact_persons(user, show_all_contact_persons, cache)

    @staticmethod
    def resolve_similar_actions(root: Action, info: GQLInfo) -> list[Action]:
        if not (lang := info.context.graphql_query_language):
            return []
        backend = get_search_backend(lang)
        if backend is None or not isinstance(backend, WatchSearchBackend):
            return []
        act_qs = Action.objects.get_queryset().visible_for_user(info.context.user)
        actions = list(backend.more_like_this(root, act_qs))
        return actions

    @staticmethod
    @gql_optimizer.resolver_hints(
        only=('status', 'implementation_phase', 'merged_with'),
        select_related=('status', 'implementation_phase'),
    )
    def resolve_status_summary(root: Action, info: GQLInfo):
        return root.get_status_summary(cache=info.context.cache)

    @staticmethod
    def resolve_timeliness(root: Action, _info: GQLInfo):
        return root.get_timeliness()

    @staticmethod
    def resolve_has_dependency_relationships(root: Action, info: GQLInfo) -> bool:
        cache = info.context.cache.for_plan_id(root.plan_id)
        if not cache.plan_has_action_dependency_roles:
            return False
        if not hasattr(root, 'has_dependencies'):
            message = (
                '[Performance issue] Calling action.resolve_has_dependency_relationships '
                'on action which has not been annotated in queryset'
            )
            logger.warning(message)
            _ = sentry_sdk.capture_message(message)
            return root.dependent_relationships.exists() or root.preceding_relationships.exists()
        return root.has_dependencies  # pyright: ignore

    @staticmethod
    def resolve_all_dependency_relationships(root: Action, info: GQLInfo):
        cache = info.context.cache.for_plan_id(root.plan_id)
        if not cache.plan_has_action_dependency_roles:
            return []
        return root.get_dependency_relationships(info.context.user, root.plan)

    @staticmethod
    @gql_optimizer.resolver_hints(
        select_related=('latest_revision', 'plan'),
        only=('latest_revision', 'has_unpublished_changes', 'plan', 'plan__features__moderation_workflow'),
        prefetch_related=prefetch_workflow_states,
    )
    def resolve_workflow_status(root: Action, info) -> Action | None:
        user = info.context.user
        plan = root.plan
        if not user.is_authenticated or not user.can_access_public_site(plan):
            return None
        return root

    @staticmethod
    def resolve_indicators_count(root: Action, _info: GQLInfo):
        inds_count = getattr(root, 'indicator_count', 0)
        return inds_count

    @staticmethod
    def resolve_has_indicators_with_goals(root: Action, _info: GQLInfo):
        goals_count = getattr(root, 'indicators_with_goals_count', 0)
        return goals_count > 0

    @staticmethod
    def resolve_datasets(root: Action, _info: GQLInfo):
        action_content_type = ContentType.objects.get_for_model(Action)
        return Dataset.objects.filter(
            scope_content_type=action_content_type,
            scope_id=root.id,
        )

    @gql_optimizer.resolver_hints(
        model_field=('primary_org'),
        select_related=('primary_org__logo'),
    )
    @staticmethod
    def resolve_primary_org(root: Action, info: GQLInfo) -> Organization | None:
        if not root.primary_org_id:
            return None
        cache = info.context.cache.for_plan_id(root.plan_id)
        org = cache.get_organization(root.primary_org_id)
        if org:
            return org
        return root.primary_org


class ActionScheduleNode(DjangoNode[ActionSchedule]):
    class Meta:
        model = ActionSchedule
        fields = public_fields(ActionSchedule)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('plan'),
    )
    def resolve_plan(root: ActionSchedule, info: GQLInfo) -> Plan | None:
        return root.plan.get_if_visible(info.context.user)


class ActionStatusNode(DjangoNode[ActionStatus]):
    class Meta:
        model = ActionStatus
        fields = public_fields(ActionStatus, add_fields=['color'])

    @staticmethod
    def resolve_color(root: ActionStatus, info: GQLInfo):
        return root.get_color(cache=info.context.cache)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('plan'),
    )
    def resolve_plan(root: ActionStatus, info: GQLInfo) -> Plan | None:
        return root.plan.get_if_visible(info.context.user)


class ActionImplementationPhaseNode(DjangoNode[ActionImplementationPhase]):
    class Meta:
        model = ActionImplementationPhase
        fields = public_fields(ActionImplementationPhase)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('plan'),
    )
    def resolve_plan(root: ActionImplementationPhase, info: GQLInfo) -> Plan | None:
        return root.plan.get_if_visible(info.context.user)


class ActionResponsiblePartyNode(DjangoNode[ActionResponsibleParty]):
    has_contact_person = graphene.Boolean(required=True)
    role = graphene.Field(ActionResponsibleParty.Role, required=False)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='organization',
    )
    def resolve_organization(root: ActionResponsibleParty, info: GQLInfo) -> Organization:
        cache = info.context.cache.for_plan_id(root.action.plan_id)
        return cache.get_organization(root.organization_id) or root.organization

    @staticmethod
    @gql_optimizer.resolver_hints(
        prefetch_related='action__contact_persons_unordered__organization',
    )
    def resolve_has_contact_person(root: ActionResponsibleParty, _info: GQLInfo) -> bool:
        return root.action.has_contact_person_from_organization(root.organization, include_suborganizations=True)

    class Meta:
        model = ActionResponsibleParty
        fields = public_fields(ActionResponsibleParty)


class ActionContactPersonNode(DjangoNode[ActionContactPerson]):
    @staticmethod
    def resolve_person(root: ActionContactPerson, info: GQLInfo) -> Person:
        cache = info.context.cache.for_plan_id(root.action.plan_id)
        person = cache.get_person(root.person_id) or root.person
        person_organization = cache.get_organization(person.organization_id)
        if person_organization is not None:
            person.organization = person_organization
        return person

    class Meta:
        model = ActionContactPerson
        fields = public_fields(ActionContactPerson)


class ActionImpactNode(DjangoNode[ActionImpact]):
    class Meta:
        model = ActionImpact
        fields = public_fields(ActionImpact)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field=('plan'),
    )
    def resolve_plan(root: ActionImpact, info: GQLInfo) -> Plan | None:
        return root.plan.get_if_visible(info.context.user)


class ActionStatusUpdateNode(DjangoNode[ActionStatusUpdate]):
    class Meta:
        model = ActionStatusUpdate
        fields = [
            'id',
            'action',
            'title',
            'date',
            'author',
            'content',
        ]


class ActionLinkNode(DjangoNode[ActionLink]):
    class Meta:
        model = ActionLink
        fields = public_fields(ActionLink)

    @staticmethod
    def resolve_url(root: ActionLink, _info: GQLInfo):
        return root.url_i18n

    @staticmethod
    def resolve_title(root: ActionLink, _info: GQLInfo):
        return root.title_i18n


def plans_actions_queryset(
    plans: Iterable[Plan], category: str | None, first: int | None, order_by: str | None, user: User | None
) -> ActionQuerySet:
    qs = Action.objects.get_queryset()
    qs = qs.visible_for_user(user).filter(plan__in=plans)
    if category is not None:
        # FIXME: This is sucky, maybe convert Category to a proper tree model?
        f = (
            Q(id=category)
            | Q(parent=category)
            | Q(parent__parent=category)
            | Q(parent__parent__parent=category)
            | Q(parent__parent__parent__parent=category)
        )
        descendant_cats = Category.objects.filter(f)
        qs = qs.filter(categories__in=descendant_cats).distinct()
    if isinstance(plans, list) and len(plans) == 1:
        plan = plans[0]
        qs = qs.annotate_related_indicator_counts(plan, user)
    qs = order_queryset(qs, ActionNode, order_by)
    if not order_by:
        qs = qs.order_by('plan', 'order')
    qs = qs.annotate_has_dependency_relationships()
    if first is not None:
        qs = qs[0:first]
    return qs


def _resolve_published_action(
    obj_id: int | None,
    identifier: str | None,
    plan_identifier: str | None,
    info: GQLInfo,
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
        action = qs.get()
    except Action.DoesNotExist:
        return None
    cache = info.context.cache.for_plan_id(action.plan_id)
    action.plan = cache.plan
    return action


def _resolve_action_revision(action: Action, desired_workflow_state: WorkflowStateEnum) -> Action:
    def with_workflow_state(match: WorkflowStateEnum, action: Action) -> Action:
        assert match != WorkflowStateEnum.PUBLISHED
        revision = action.latest_revision
        assert revision is not None
        revision_action = revision.as_object()
        revision_action.updated_at = revision.created_at
        revision_action._actual_workflow_state = match
        return revision_action

    def published(action: Action) -> Action:
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
    if desired_workflow_state == WorkflowStateEnum.APPROVED and available_revision_state == WorkflowStateEnum.APPROVED:
        return with_workflow_state(available_revision_state, action)

    # User wants published version or no other appropriate version available
    return published(action)


class Query:
    plan = gql_optimizer.field(graphene.Field(PlanNode, id=graphene.ID(), domain=graphene.String()))
    plans_for_hostname = graphene.List(graphene.NonNull(PlanInterface), hostname=graphene.String())
    plans = graphene.List(graphene.NonNull(PlanNode))
    my_plans = graphene.List(PlanNode)

    action = graphene.Field(ActionNode, id=graphene.ID(), identifier=graphene.ID(), plan=graphene.ID())

    plan_actions = graphene.List(
        graphene.NonNull(ActionNode),
        plan=graphene.ID(required=True),
        first=graphene.Int(),
        category=graphene.ID(),
        order_by=graphene.String(),
        restrict_to_publicly_visible=graphene.Boolean(default_value=True),
    )
    related_plan_actions = graphene.List(
        graphene.NonNull(ActionNode),
        plan=graphene.ID(required=True),
        first=graphene.Int(),
        category=graphene.ID(),
        order_by=graphene.String(),
    )
    plan_categories = graphene.List(
        graphene.NonNull(CategoryNode),
        plan=graphene.ID(required=True),
        category_type=graphene.ID(),
    )

    category = graphene.Field(
        CategoryNode,
        plan=graphene.ID(required=True),
        category_type=graphene.ID(required=True),
        external_identifier=graphene.ID(required=True),
    )

    workflow_states = graphene.List(
        WorkflowStateDescription,
        plan=graphene.ID(required=False),
    )

    pledge_user = graphene.Field(
        PledgeUserNode,
        uuid=graphene.UUID(required=True),
        description="Get a pledge user by UUID to retrieve their commitments",
    )

    @staticmethod
    def resolve_pledge_user(_root: Query, info: GQLInfo, uuid: uuid.UUID) -> PledgeUser | None:
        return PledgeUser.objects.filter(uuid=uuid).first()

    @staticmethod
    def resolve_workflow_states(_root: Query, info: GQLInfo, plan: str | None):
        if plan is None:
            return []
        user = user_or_none(info.context.user)
        result = []
        plan_obj = Plan.objects.get(identifier=plan)
        if plan_obj.features.moderation_workflow is None:
            return []
        tasks = plan_obj.get_workflow_tasks()
        if user is None or not user.can_access_public_site(plan_obj):
            result = [WorkflowStateEnum.PUBLISHED]
        elif user.can_access_admin(plan_obj):
            if tasks.count() > 1:
                result = [WorkflowStateEnum.PUBLISHED, WorkflowStateEnum.APPROVED, WorkflowStateEnum.DRAFT]
            else:
                result = [WorkflowStateEnum.PUBLISHED, WorkflowStateEnum.DRAFT]
        elif user.can_access_public_site(plan_obj):
            if tasks.count() > 1:
                result = [WorkflowStateEnum.PUBLISHED, WorkflowStateEnum.DRAFT]
            else:
                result = [WorkflowStateEnum.PUBLISHED]
        return [
            {
                'id': e.name,
                'description': WorkflowStateEnum(e).description,
            }
            for e in result
        ]

    @staticmethod
    def resolve_plan(_root: Query, info: GQLInfo, id: str | None = None, domain: str | None = None, **_kwargs) -> Plan | None:
        if not id and not domain:
            raise GraphQLError("You must supply either id or domain as arguments to 'plan'")

        qs = Plan.objects.get_queryset().visible_for_user(info.context.user)
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
    def resolve_plans_for_hostname(_root: Query, info: GQLInfo, hostname: str) -> list[Plan]:
        info.context._plan_hostname = hostname.lower()  # type: ignore
        plans = Plan.objects.get_queryset().for_hostname(
            info.context._plan_hostname,
            request=info.context,  # type: ignore
        )
        ret = list(gql_optimizer.query(plans, info))
        req = info.context
        if not ret:
            logger.info('No plans found for hostname %s (wildcard domains: %s)' % (hostname, req.wildcard_domains))
        return ret

    @staticmethod
    def resolve_plans(_root: Query, info: GQLInfo) -> list[Plan]:
        user = user_or_none(info.context.user)
        if user is None or not user.is_superuser:
            return []

        qs = Plan.objects.get_queryset().visible_for_user(info.context.user)
        return list(qs)

    @staticmethod
    def resolve_my_plans(_root, info: GQLInfo):
        user = user_or_none(info.context.user)
        if user is None:
            return []
        plans = Plan.objects.get_queryset().user_has_staff_role_for(user)
        return gql_optimizer.query(plans, info)

    @staticmethod
    def _resolve_plan_action_revisions(
        plan: Plan,
        desired_workflow_state: WorkflowStateEnum,
        action_queryset: ActionQuerySet,
        cache: PlanSpecificCache,
    ):
        ct = ContentType.objects.get_for_model(Action)
        revision_pks: list[int] = []
        actions_without_revision: Iterable[Action] = []
        if desired_workflow_state == WorkflowStateEnum.DRAFT:
            revision_pks = list(action_queryset.filter(has_unpublished_changes=True).values_list('latest_revision_id', flat=True))
            actions_without_revision = action_queryset.filter(has_unpublished_changes=False)
        elif desired_workflow_state == WorkflowStateEnum.APPROVED:
            desired_workflow_task = plan.get_next_workflow_task(desired_workflow_state)
            action_pks = [str(pk) for pk in action_queryset.values_list('pk', flat=True)]
            if desired_workflow_task is not None:
                workflowstates = (
                    WorkflowState._default_manager.get_queryset()
                    .active()
                    .filter(content_type=ct)
                    .filter(current_task_state__task=desired_workflow_task)
                    .filter(object_id__in=action_pks)
                )
                actions_with_revision_pks = workflowstates.values_list('object_id', flat=True)
                actions_without_revision = action_queryset.exclude(pk__in=[int(pk) for pk in actions_with_revision_pks])
                revision_pks = list(workflowstates.values_list('current_task_state__revision_id', flat=True))
        revision_qs = Revision.objects.filter(pk__in=revision_pks).prefetch_related('content_object__plan')
        actions: list[Action] = []
        for rev in revision_qs:
            content = SerializedDictWithRelatedObjectCache[str, Any](rev.content, cache=cache)
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
        for action in actions_without_revision:
            cache.enrich_action(action)
            actions.append(action)
        return sorted(actions, key=lambda o: o.order)

    @staticmethod
    def resolve_plan_actions(
        _root,
        info: GQLInfo,
        plan: str,
        first: int | None = None,
        category: str | None = None,
        order_by: str | None = None,
        restrict_to_publicly_visible: bool = True,
        **_kwargs,
    ) -> Iterable[Action] | None:
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        user = user_or_none(info.context.user)
        if not plan_obj.is_visible_for_user(user):
            return None

        workflow_state = info.context.cache.query_workflow_state
        qs = gql_optimizer.query(
            plans_actions_queryset(
                [plan_obj],
                category,
                first,
                order_by,
                user,
            ),
            info,
        )

        cache = info.context.cache.for_plan(plan_obj)
        persons_queryset = Person.objects.get_queryset().filter(actioncontactperson__action__plan=plan_obj).distinct()
        cache.populate_persons(persons_queryset)
        cache.populate_organizations(
            Organization.objects.get_queryset()
            .filter(Q(responsible_actions__action__plan=plan_obj) | Q(people__in=persons_queryset))
            .distinct()
            .select_related('logo')
            .prefetch_related(Prefetch('logo__renditions', to_attr='prefetched_renditions'))
        )
        if not is_authenticated(user):
            workflow_state = WorkflowStateEnum.PUBLISHED
        elif not user.can_access_public_site(plan=plan_obj):
            workflow_state = WorkflowStateEnum.PUBLISHED
        if workflow_state == WorkflowStateEnum.PUBLISHED:
            actions = []
            for act in qs:
                cache.enrich_action(act)
                actions.append(act)
            return actions
        ret = Query._resolve_plan_action_revisions(plan_obj, workflow_state, qs, cache=cache)
        return ret

    @staticmethod
    def resolve_related_plan_actions(_root, info, plan, first=None, category=None, order_by=None, **_kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        user = info.context.user
        if not plan_obj.is_visible_for_user(user):
            return None

        plans = plan_obj.get_all_related_plans().visible_for_user(user)
        qs = plans_actions_queryset(plans, category, first, order_by, user)
        return gql_optimizer.query(qs, info)

    @staticmethod
    def resolve_plan_categories(_root, info, plan, **kwargs):
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        if not plan_obj.is_visible_for_user(info.context.user):
            return None

        qs = Category.objects.filter(type__plan=plan_obj)

        category_type = kwargs.get('category_type')
        if category_type is not None:
            qs = qs.filter(type__identifier=category_type)

        return gql_optimizer.query(qs, info)

    @staticmethod
    def resolve_action(
        _root,
        info: GQLInfo,
        id: int | None = None,
        identifier: str | None = None,
        plan: str | None = None,
    ) -> Action | None:
        workflow_state = info.context.cache.query_workflow_state
        action = _resolve_published_action(id, identifier, plan, info)

        if action and not identifier:
            set_active_plan(info, action.plan)

        plan_obj = action.plan if action else None
        if plan_obj is None:
            return action

        user = info.context.user
        if not plan_obj.is_visible_for_user(user):
            return None

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
    def resolve_category(_root, info: GQLInfo, plan: str, category_type: str, external_identifier: str) -> Category | None:
        plan_obj = get_plan_from_context(info, plan)
        if not plan_obj:
            return None

        if not plan_obj.is_visible_for_user(info.context.user):
            return None

        return Category.objects.get(
            type__plan=plan_obj,
            type__identifier=category_type,
            external_identifier=external_identifier,
        )


class RegisterPledgeUserPayload(graphene.ObjectType[Any]):
    """Payload returned after registering a pledge user."""

    uuid = graphene.UUID(required=True)


class RegisterPledgeUserMutation(graphene.Mutation):
    """Create a new anonymous PledgeUser."""

    Output = RegisterPledgeUserPayload

    @classmethod
    def mutate(cls, _root, _info: GQLInfo) -> RegisterPledgeUserPayload:
        pledge_user = PledgeUser.objects.create()
        return RegisterPledgeUserPayload(uuid=pledge_user.uuid)


class CommitToPledgePayload(graphene.ObjectType[Any]):
    """Payload returned after committing to or uncommitting from a pledge."""

    committed = graphene.Boolean(required=True)


class CommitToPledgeMutation(graphene.Mutation):
    """Create or remove a commitment to a pledge."""

    class Arguments:
        user_uuid = graphene.UUID(required=True, description="UUID of the PledgeUser")
        pledge_id = graphene.ID(required=True, description="ID of the Pledge")
        committed = graphene.Boolean(required=True, description="True to commit, False to uncommit")

    Output = CommitToPledgePayload

    @classmethod
    def mutate(cls, _root, _info: GQLInfo, user_uuid: uuid.UUID, pledge_id: str, committed: bool) -> CommitToPledgePayload:
        # Get the PledgeUser
        try:
            pledge_user = PledgeUser.objects.get(uuid=user_uuid)
        except PledgeUser.DoesNotExist:
            raise GraphQLError("PledgeUser not found") from None

        # Get the Pledge
        try:
            pledge = Pledge.objects.select_related('plan__features').get(id=pledge_id)
        except Pledge.DoesNotExist:
            raise GraphQLError("Pledge not found") from None

        # Check that community engagement is enabled for this plan
        if not pledge.plan.features.enable_community_engagement:
            raise GraphQLError("Community engagement is not enabled for this plan") from None

        if committed:
            # Create commitment (ignore if already exists)
            PledgeCommitment.objects.get_or_create(
                pledge=pledge,
                pledge_user=pledge_user,
            )
        else:
            # Remove commitment if it exists
            PledgeCommitment.objects.filter(
                pledge=pledge,
                pledge_user=pledge_user,
            ).delete()

        pledge.plan.invalidate_cache()
        return CommitToPledgePayload(committed=committed)


class SetUserDataPayload(graphene.ObjectType[Any]):
    """Payload returned after setting user data."""

    uuid = graphene.UUID(required=True)


class SetUserDataMutation(graphene.Mutation):
    """Set a key-value pair in a PledgeUser's user_data."""

    class Arguments:
        user_uuid = graphene.UUID(required=True, description="UUID of the PledgeUser")
        key = graphene.String(required=True, description="Key to set in user_data")
        value = graphene.String(required=True, description="Value to set for the key")

    Output = SetUserDataPayload

    @classmethod
    def mutate(cls, _root, _info: GQLInfo, user_uuid: uuid.UUID, key: str, value: str) -> SetUserDataPayload:
        try:
            pledge_user = PledgeUser.objects.get(uuid=user_uuid)
        except PledgeUser.DoesNotExist:
            raise GraphQLError("PledgeUser not found") from None

        pledge_user.user_data[key] = value
        pledge_user.save(update_fields=['user_data'])

        return SetUserDataPayload(uuid=pledge_user.uuid)


class PledgeMutations(graphene.ObjectType[Any]):
    """Mutations related to pledges and community engagement."""

    register_user = RegisterPledgeUserMutation.Field(
        description="Register a new anonymous pledge user; returns the UUID for the created user",
    )
    commit_to_pledge = CommitToPledgeMutation.Field(
        description="Commit to or uncommit from a pledge",
    )
    set_user_data = SetUserDataMutation.Field(
        description="Set a key-value pair in a PledgeUser's user_data.",
    )


def get_plan_mutation_namespace():
    from .mutations import PlanMutations

    return PlanMutations


def get_action_mutation_namespace():
    from .mutations_action import ActionMutations

    return ActionMutations


class Mutation(graphene.ObjectType[Any]):
    pledge = graphene.Field(PledgeMutations, required=True)

    @staticmethod
    def resolve_pledge(root, info: GQLInfo) -> PledgeMutations:
        return PledgeMutations()

    plan = graphene.Field(graphene.NonNull(get_plan_mutation_namespace))
    action = graphene.Field(graphene.NonNull(get_action_mutation_namespace))

    @staticmethod
    def resolve_plan(root, info: GQLInfo):
        user = user_or_none(info.context.user)
        if user is None or not user.is_superuser:
            raise PermissionDeniedError(info, "Superuser required for this operation.")
        return get_plan_mutation_namespace()()

    @staticmethod
    def resolve_action(root, info: GQLInfo):
        user = user_or_none(info.context.user)
        if user is None or not user.is_superuser:
            raise PermissionDeniedError(info, "Superuser required for this operation.")
        return get_action_mutation_namespace()()


@sb.type
class PlanUpdate:
    identifier: sb.ID
    cache_invalidated_at: datetime


@sb.type
class Subscription:
    @sb.subscription
    async def plan_cache_invalidations(self, info: gql.Info) -> AsyncGenerator[list[PlanUpdate]]:
        ws = info.context.get_ws_consumer()
        channel_layer = ws.channel_layer
        if channel_layer is None:
            raise ValueError("Channel layer is not available")
        await channel_layer.group_add('plan_cache_invalidations', ws.channel_name)
        async with ws.listen_to_channel('plan.cache_invalidated') as listener:
            async for message in listener:
                plan_identifier = message.get('plan_identifier')
                if plan_identifier is None:
                    continue
                invalidated_at = message.get('invalidated_at')
                if invalidated_at is None:
                    continue
                yield [PlanUpdate(identifier=plan_identifier, cache_invalidated_at=datetime.fromisoformat(invalidated_at))]
