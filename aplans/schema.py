from __future__ import annotations

import dataclasses
from typing import Any

import graphene
from wagtail.models import Page
from wagtail.models.i18n import Locale
from wagtail.models.sites import Site
from actions.models.category import Category, CategoryType
from indicators.models import ActionIndicator, Indicator, IndicatorLevel, Unit
import strawberry as sb
from django.db.models import Count, Q
from django.utils.text import slugify
from graphql import DirectiveLocation
from graphql.error import GraphQLError
from graphql.type import (
    GraphQLArgument,
    GraphQLDirective,
    GraphQLNonNull,
    GraphQLString,
    specified_directives,
)
from strawberry.tools import merge_types
from strawberry.types.field import StrawberryField

import graphene_django_optimizer as gql_optimizer
from grapple.registry import registry as grapple_registry

from kausal_common.deployment import test_mode_enabled
from kausal_common.graphene.strawberry_schema import CombinedSchema
from kausal_common.strawberry.registry import register_strawberry_type
from kausal_common.testing.schema import TestModeMutation, TestModeNotEnabledError

from aplans.cache import OrganizationActionCountCache
from aplans.graphql_types import WorkflowStateGrapheneEnum
from aplans.utils import public_fields

from actions import schema as actions_schema
from actions.models import Plan
from actions.models.action import Action, ActionCategoryThrough
from content.models import SiteGeneralContent
from datasets import schema as datasets_schema
from feedback import schema as feedback_schema
from indicators import schema as indicators_schema
from orgs import schema as orgs_schema
from orgs.models import Organization
from pages import schema as pages_schema
from pages.models import ActionListPage, CategoryPage, CategoryTypePage, EmptyPage, IndicatorListPage, PlanRootPage, StaticPage
from people import schema as people_schema
from people.models import Person
from reports import schema as reports_schema
from search import schema as search_schema

from . import graphql_gis  # noqa
from .graphql_helpers import get_fields
from .graphql_types import DjangoNode, GQLInfo, WorkflowStateEnum, get_plan_from_context, graphene_registry


def mp_node_get_ancestors(qs, include_self=False):
    # https://github.com/django-treebeard/django-treebeard/issues/98
    paths = set()
    for node in qs:
        length = len(node.path)
        if include_self:
            length += node.steplen
        paths.update(node.path[0:pos]
                     for pos in range(node.steplen, length, node.steplen))
    return qs.model.objects.filter(path__in=paths)


class SiteGeneralContentNode(DjangoNode):
    class Meta:
        model = SiteGeneralContent
        fields = public_fields(SiteGeneralContent)


class Query(
    actions_schema.Query,
    indicators_schema.Query,
    orgs_schema.Query,
    pages_schema.Query,
    reports_schema.Query,
    datasets_schema.Query,
    search_schema.Query,
    graphene.ObjectType,
):
    plan_organizations = graphene.List(
        graphene.NonNull(orgs_schema.OrganizationNode),
        plan=graphene.ID(),
        with_ancestors=graphene.Boolean(default_value=False),
        for_responsible_parties=graphene.Boolean(default_value=True),
        for_contact_persons=graphene.Boolean(default_value=False),
        include_related_plans=graphene.Boolean(default_value=False),
    )
    person = graphene.Field(people_schema.PersonNode, id=graphene.ID(required=True))

    def resolve_plan_organizations(
        self, info: GQLInfo, plan: str | None, with_ancestors: bool, for_responsible_parties: bool, for_contact_persons: bool,
        include_related_plans: bool, **kwargs,
    ):
        plan_obj: Plan | None = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        if include_related_plans:
            plans = list(plan_obj.get_all_related_plans(inclusive=True))
        else:
            plans = [plan_obj]

        visible_actions = Action.objects.visible_for_user(info.context.user).filter(plan__in=plans)

        workflow_state = getattr(info.context.watch_cache, 'query_workflow_state', None)
        some_plan_has_a_workflow = any(p.features.moderation_workflow is not None for p in plans)
        consider_responsible_parties_within_action_revisions = (
            workflow_state is not None and
            workflow_state != WorkflowStateEnum.PUBLISHED and
            some_plan_has_a_workflow
        )
        cache = None
        if consider_responsible_parties_within_action_revisions:
            info.context.organization_action_count_cache = OrganizationActionCountCache(visible_actions)
            cache = info.context.organization_action_count_cache

        qs = Organization.objects.available_for_plans(plans)
        if plan is not None:
            # Note the weird behavior by Django: Q() is neither "true" nor "false".
            # For all x, Q() | x is equivalent to x, and Q() & x is also equivalent to x.
            query = Q()
            if for_responsible_parties:
                if consider_responsible_parties_within_action_revisions:
                    responsible_actions_filter = cache.organization_responsible_party_queryset_filter
                else:
                    responsible_actions_filter = Q(responsible_actions__action__in=visible_actions)
                query |= responsible_actions_filter
            if for_contact_persons:
                query |= Q(people__contact_for_actions__in=visible_actions)
            if not query and not info.context.user.is_authenticated:
                raise GraphQLError("Unfiltered organization list only available when authenticated")
            qs = qs.filter(query)
        qs = qs.distinct()

        if with_ancestors:
            if plan is None:
                raise GraphQLError("withAncestors can only be used when 'plan' is set")
            qs = mp_node_get_ancestors(qs, include_self=True)

        selections = get_fields(info)
        if 'actionCount' in selections:
            if not consider_responsible_parties_within_action_revisions:
                annotate_filter = Q(responsible_actions__action__in=visible_actions)
                qs = qs.annotate(action_count=Count(
                    'responsible_actions__action', distinct=True, filter=annotate_filter,
                ))

        if 'contactPersonCount' in selections and plan_obj.features.public_contact_persons:
            # FIXME: Check visibility of related plans, too
            annotate_filter = Q(people__contact_for_actions__in=visible_actions)
            qs = qs.annotate(contact_person_count=Count(
                'people', distinct=True, filter=annotate_filter,
            ))

        qs = gql_optimizer.query(qs, info)

        if with_ancestors:
            # Slight optimization that should prevent org.get_parent() from
            # resulting in a new DB hit.
            orgs_by_path = {org.path: org for org in qs}
            org: Organization
            for org in qs:
                depth = int(len(org.path) / org.steplen)
                if depth <= 1:
                    continue
                parent_path = org._get_basepath(org.path, depth - 1)
                parent = orgs_by_path.get(parent_path)
                if parent is not None:
                    org._cached_parent_obj = parent

        return qs

    def resolve_person(self, info, **kwargs):
        qs = Person.objects.all()
        obj_id = kwargs.get('id')
        qs = qs.filter(id=obj_id)
        try:
            obj = qs.get()
        except Person.DoesNotExist:
            return None

        return obj


class Mutation(
    actions_schema.Mutation,
    indicators_schema.Mutation,
    orgs_schema.Mutation,
    people_schema.Mutation,
    graphene.ObjectType,
):
    create_user_feedback = feedback_schema.UserFeedbackMutation.Field()


LocaleDirective = GraphQLDirective(
    name='locale',
    description='Select locale in which to return data',
    args={
        'lang': GraphQLArgument(
            type_=GraphQLNonNull(GraphQLString),
            description="Language code of the locale to use",
        ),
    },
    locations=[DirectiveLocation.QUERY],
)


AuthDirective = GraphQLDirective(
    name='auth',
    description="Provide authentication data",
    args={
        'uuid': GraphQLArgument(
            type_=GraphQLNonNull(GraphQLString),
            description="User UUID",
        ),
        'token': GraphQLArgument(
            type_=GraphQLNonNull(GraphQLString),
            description="Authentication token",
        ),
    },
    locations=[DirectiveLocation.MUTATION],
)

graphene_enum_type = graphene.types.schema.TypeMap.create_enum(WorkflowStateGrapheneEnum)


WorkflowStateDirective = GraphQLDirective(
    name='workflow',
    description=(
        'Let the client request retrieving approved/unapproved '
        'drafts or published versions of plan data (currently individual actions). '
        'The actual response is dependent on user access rights, for example '
        'a published version is always returned to unauthenticated users '
        'or when no draft exists.'
    ),
    args={
        'state':
        GraphQLArgument(
            type_= graphene_enum_type,
            description="State of content to show",
            default_value=WorkflowStateEnum.PUBLISHED,
        ),
    },
    locations=[DirectiveLocation.QUERY],
)


@sb.type(name='Query')
class SBQuery:
    dummy: None  # Strawberry Queries must have some fields, but we have not yet migrated our queries from Graphene


@sb.type
class BaseModelType:
    def __init__(self, obj: Any, private_field_name: str):
        setattr(self, private_field_name, obj)
        proper_fields = [
            field.name for field in dataclasses.fields(self)
            if not isinstance(field, StrawberryField)
            and field.name != private_field_name
        ]
        for field in proper_fields:
            setattr(self, field, getattr(obj, field))


# FIXME: We have two GraphQL types for representing organizations -- this one and OrganizationNode (for Graphene). I'm
# not sure if or how we can use a Graphene type in a Strawberry query / mutation.
@register_strawberry_type
@sb.type
class OrganizationType(BaseModelType):
    id: int
    uuid: str
    name: str

    _org: sb.Private[Organization]

    def __init__(self, organization: Organization):
        super().__init__(organization, '_org')


# FIXME: We have two GraphQL types for representing plans -- this one and PlanNode (for Graphene). I'm not sure if or
# how we can use a Graphene type in a Strawberry query / mutation.
@register_strawberry_type
@sb.type
class PlanType(BaseModelType):
    id: int
    identifier: str

    _plan: sb.Private[Plan]

    def __init__(self, plan: Plan):
        super().__init__(plan, '_plan')


@register_strawberry_type
@sb.type
class ActionType(BaseModelType):
    id: int
    uuid: str
    name: str
    identifier: str
    plan_id: int

    _action: sb.Private[Action]

    def __init__(self, action: Action):
        super().__init__(action, '_action')


@register_strawberry_type
@sb.type
class CategoryModelType(BaseModelType):
    id: int
    name: str
    identifier: str
    type_id: int

    _category: sb.Private[Category]

    def __init__(self, category: Category):
        super().__init__(category, '_category')


@register_strawberry_type
@sb.type
class IndicatorType(BaseModelType):
    id: int
    name: str
    uuid: str
    organization_id: int

    _indicator: sb.Private[Indicator]

    def __init__(self, indicator: Indicator):
        super().__init__(indicator, '_indicator')


@register_strawberry_type
@sb.type
class PageType(BaseModelType):
    id: int
    title: str
    url_path: str

    _page: sb.Private[Any]

    def __init__(self, page: Any):
        super().__init__(page, '_page')


@register_strawberry_type
@sb.type
class CategoryTypeModelType(BaseModelType):
    id: int
    name: str
    identifier: str
    plan_id: int

    _category_type: sb.Private[CategoryType]

    def __init__(self, category_type: CategoryType):
        super().__init__(category_type, '_category_type')


@sb.type
class WatchTestModeMutation(TestModeMutation):
    @sb.mutation
    def create_organization(self, name: str) -> OrganizationType:
        org = Organization(name=name)
        Organization.add_root(instance=org)
        return OrganizationType(org)

    @sb.mutation
    def create_plan(self, identifier: str, name: str, organization_uuid: str) -> PlanType:
        org = Organization.objects.get(uuid=organization_uuid)
        plan = Plan.objects.create(organization=org, identifier=identifier, name=name)
        return PlanType(plan)

    @sb.mutation
    def create_action(self, plan_identifier: str, name: str, identifier: str) -> ActionType:
        plan = Plan.objects.get(identifier=plan_identifier)
        action = Action.objects.create(
            plan=plan,
            name=name,
            identifier=identifier
        )
        return ActionType(action)

    @sb.mutation
    def create_category_type(
        self, plan_identifier: str, name: str, identifier: str, usable_for_actions: bool = True) -> CategoryTypeModelType:
        plan = Plan.objects.get(identifier=plan_identifier)
        category_type = CategoryType.objects.create(
            plan=plan,
            name=name,
            identifier=identifier,
            usable_for_actions=usable_for_actions
        )
        return CategoryTypeModelType(category_type)

    @sb.mutation
    def create_category(
        self, plan_identifier: str, category_type_identifier: str, name: str, identifier: str) -> CategoryModelType:
        plan = Plan.objects.get(identifier=plan_identifier)
        category_type = CategoryType.objects.get(plan=plan, identifier=category_type_identifier)
        category = Category.objects.create(
            type=category_type,
            name=name,
            identifier=identifier
        )
        return CategoryModelType(category)

    @sb.mutation
    def create_indicator(self, plan_identifier: str, name: str, organization_uuid: str | None = None) -> IndicatorType:
        plan = Plan.objects.get(identifier=plan_identifier)

        if organization_uuid:
            org = Organization.objects.get(uuid=organization_uuid)
        else:
            org = plan.organization

        unit, _ = Unit.objects.get_or_create(name="Count")

        indicator = Indicator.objects.create(
            name=name,
            organization=org,
            unit=unit
        )

        IndicatorLevel.objects.create(
            indicator=indicator,
            plan=plan,
            level='strategic'
        )

        return IndicatorType(indicator)

    @sb.mutation
    def link_action_to_category(self, action_id: int, category_id: int) -> bool:
        action = Action.objects.get(id=action_id)
        category = Category.objects.get(id=category_id)
        ActionCategoryThrough.objects.create(
            action=action,
            category=category
        )
        return True

    @sb.mutation
    def link_action_to_indicator(self, action_id: int, indicator_id: int) -> bool:
        action = Action.objects.get(id=action_id)
        indicator = Indicator.objects.get(id=indicator_id)
        ActionIndicator.objects.create(
            action=action,
            indicator=indicator,
            effect_type="increases"
        )
        return True


    @sb.mutation
    def create_plan_root_page(self, plan_identifier: str, title: str, locale: str = "en") -> PageType:
        plan = Plan.objects.get(identifier=plan_identifier)
        # Use the plan's primary language if available, otherwise use provided locale
        language_code = getattr(plan, 'primary_language', locale)

        # Get or create the locale
        try:
            locale_obj = Locale.objects.get(language_code__iexact=language_code)
        except Locale.DoesNotExist:
            # Fall back to English if the requested locale doesn't exist
            locale_obj = Locale.objects.get(language_code='en')

        # Create root page with proper locale
        root_page = PlanRootPage(
            title=title,
            show_in_menus=False,
            locale=locale_obj
        )

        # Add root page as child of Wagtail root
        wagtail_root = Page.objects.get(id=1)
        wagtail_root.add_child(instance=root_page)

        # Create or update the site for this plan
        hostname = f"{plan.identifier}.example.com"  # Example hostname

        if hasattr(plan, 'site') and plan.site:
            # Update existing site
            plan.site.hostname = hostname
            plan.site.root_page = root_page
            plan.site.save()
        else:
            # Create new site
            site = Site.objects.create(
                hostname=hostname,
                root_page=root_page,
                is_default_site=False
            )
            # Link the site to the plan
            plan.site = site
            plan.save()

        return PageType(root_page)


    @sb.mutation
    def create_action_list_page(self, plan_identifier: str, title: str) -> PageType:
        plan = Plan.objects.get(identifier=plan_identifier)

        # Check if the plan has a root page
        if not plan.root_page:
            raise ValueError("Plan has no root page. Create one first with create_plan_root_page.")

        # Check if an ActionListPage already exists
        existing_page = Page.objects.descendant_of(plan.root_page).filter(slug='actions').first()
        if existing_page:
            return PageType(existing_page.specific)

        # Create a new page
        page = ActionListPage(
            title=title,
            show_in_menus=True
        )

        # Add as child of plan's root page
        plan.root_page.add_child(instance=page)

        # Set default content blocks
        page.set_default_content_blocks()

        return PageType(page)

    @sb.mutation
    def create_indicator_list_page(self, plan_identifier: str, title: str) -> PageType:
        plan = Plan.objects.get(identifier=plan_identifier)

        # Check if the plan has a root page
        if not plan.root_page:
            raise ValueError("Plan has no root page. Create one first with create_plan_root_page.")

        # Check if an IndicatorListPage already exists
        existing_page = Page.objects.descendant_of(plan.root_page).filter(slug='indicators').first()
        if existing_page:
            return PageType(existing_page.specific)

        # Create page
        page = IndicatorListPage(
            title=title,
            show_in_menus=True
        )

        # Add as child of plan's root page
        plan.root_page.add_child(instance=page)

        return PageType(page)

    @sb.mutation
    def create_empty_page(self, plan_identifier: str, title: str, parent_id: int | None = None) -> PageType:
        plan = Plan.objects.get(identifier=plan_identifier)

        # Check if the plan has a root page
        if not plan.root_page:
            raise ValueError("Plan has no root page. Create one first with create_plan_root_page.")

        # Determine parent page
        if parent_id:
            parent = Page.objects.get(id=parent_id)
        else:
            parent = plan.root_page

        # Create page
        page = EmptyPage(
            title=title,
            show_in_menus=True,
            slug=slugify(title)
        )

        parent.add_child(instance=page)
        return PageType(page)

    @sb.mutation
    def create_static_page(self, plan_identifier: str, title: str, parent_id: int | None = None) -> PageType:
        plan = Plan.objects.get(identifier=plan_identifier)

        # Check if the plan has a root page
        if not plan.root_page:
            raise ValueError("Plan has no root page. Create one first with create_plan_root_page.")

        # Determine parent page
        if parent_id:
            parent = Page.objects.get(id=parent_id)
        else:
            parent = plan.root_page

        # Create page
        page = StaticPage(
            title=title,
            show_in_menus=True,
            slug=slugify(title)
        )

        parent.add_child(instance=page)
        return PageType(page)

    @sb.mutation
    def create_category_type_page(self, plan_identifier: str, title: str, category_type_id: int) -> PageType:
        plan = Plan.objects.get(identifier=plan_identifier)
        category_type = CategoryType.objects.get(id=category_type_id)

        # Check if the plan has a root page
        if not plan.root_page:
            raise ValueError("Plan has no root page. Create one first with create_plan_root_page.")

        # Check if a page for this category type already exists
        existing_page = CategoryTypePage.objects.filter(category_type=category_type).first()
        if existing_page:
            return PageType(existing_page)

        # Create page
        page = CategoryTypePage(
            title=title,
            category_type=category_type,
            show_in_menus=True,
            slug=slugify(title)
        )

        # Add to root page
        plan.root_page.add_child(instance=page)

        return PageType(page)

    @sb.mutation
    def create_category_page(self, plan_identifier: str, title: str, category_id: int) -> PageType:
        plan = Plan.objects.get(identifier=plan_identifier)
        category = Category.objects.get(id=category_id)

        # Check if the plan has a root page
        if not plan.root_page:
            raise ValueError("Plan has no root page. Create one first with create_plan_root_page.")

        # Check if a page for this category already exists
        existing_page = CategoryPage.objects.filter(category=category).first()
        if existing_page:
            return PageType(existing_page)

        type_page = CategoryTypePage.objects.filter(
            category_type=category.type
        ).first()

        # Determine parent - use type page if available, otherwise root page
        parent = type_page if type_page else plan.root_page

        # Create page with category
        page = CategoryPage(
            title=title,
            category=category,
            show_in_menus=True,
            slug=slugify(title)
        )

        parent.add_child(instance=page)

        return PageType(page)


@sb.type
class WatchTestModeMutations:
    @sb.field
    def test_mode(self) -> WatchTestModeMutation:
        if not test_mode_enabled():
            raise TestModeNotEnabledError()
        return WatchTestModeMutation()


SB_MUTATION_TYPES: list[type] = []
if test_mode_enabled():
    SB_MUTATION_TYPES.append(WatchTestModeMutations)

SBMutation: type | None = None
if SB_MUTATION_TYPES:
    SBMutation = merge_types('Mutation', tuple(SB_MUTATION_TYPES))


def generate_strawberry_schema() -> sb.Schema:
    from kausal_common.strawberry.registry import strawberry_types

    sb_schema = sb.Schema(
        query=SBQuery, mutation=SBMutation, types=strawberry_types, directives=[]
    )
    return sb_schema


def generate_schema() -> tuple[sb.Schema, CombinedSchema]:
    # We generate the Strawberry schema just to be able to utilize the
    # resolved GraphQL types directly in the Graphene schema.
    sb_schema = generate_strawberry_schema()

    schema = CombinedSchema(
        sb_schema=sb_schema,
        query=Query,
        mutation=Mutation,
        directives=list(specified_directives) + [LocaleDirective, AuthDirective, WorkflowStateDirective],
        types=list(grapple_registry.models.values()) + graphene_registry,
    )
    return sb_schema, schema


sb_schema, schema = generate_schema()
