from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, cast

import graphene
import strawberry as sb
from django.db.models import Count, Q
from graphql import DirectiveLocation
from graphql.error import GraphQLError
from graphql.type import (
    GraphQLArgument,
    GraphQLDirective,
)
from strawberry.schema import Schema as StrawberrySchema
from strawberry.tools import merge_types
from strawberry.types import has_object_definition

import graphene_django_optimizer as gql_optimizer
from grapple.registry import registry as grapple_registry
from treebeard.mp_tree import MP_NodeQuerySet

from kausal_common.deployment import test_mode_enabled
from kausal_common.graphene.utils import get_graphene_meta
from kausal_common.models.types import copy_signature
from kausal_common.strawberry.extensions import LoggingTracingExtension
from kausal_common.strawberry.schema import Schema as UnifiedSchema
from kausal_common.users import user_or_none
from kausal_common.users.schema import UserNode

from aplans import gql
from aplans.cache import OrganizationActionCountCache
from aplans.graphql_types import WorkflowStateGrapheneEnum
from aplans.schema_context import WatchGraphQLContext
from aplans.utils import public_fields

from people.models import Person

if True:  # so that import re-ordering won't touch these
    # These imports need to be before `actions_schema` and others,
    # because they introduce new some new converter types and patch
    # the Image-related grapple types.
    from kausal_common import graphql_gis  # noqa: F401

    from images import schema as images_schema  # noqa: F401

from actions import schema as actions_schema
from actions.graphql_admin_schema import AdminQuery
from actions.models.action import Action
from content.models import SiteGeneralContent
from datasets import schema as datasets_schema
from feedback import schema as feedback_schema
from indicators import schema as indicators_schema
from orgs import schema as orgs_schema
from orgs.models import Organization
from pages import schema as pages_schema
from people import schema as people_schema
from reports import schema as reports_schema
from search import schema as search_schema
from users import schema as users_schema

from .graphql_helpers import get_fields
from .graphql_types import DjangoNode, WorkflowStateEnum, get_plan_from_context

if TYPE_CHECKING:
    from collections.abc import Iterable

    from aplans.graphql_types import GQLInfo

    from actions.models import Plan
    from users.models import User

def mp_node_get_ancestors[QS: MP_NodeQuerySet[Any]](qs: QS, include_self: bool = False) -> QS:
    # https://github.com/django-treebeard/django-treebeard/issues/98
    paths: set[str] = set()
    for node in qs:
        length = len(node.path)
        if include_self:
            length += node.steplen
        paths.update(node.path[0:pos]
                     for pos in range(node.steplen, length, node.steplen))
    return cast('QS', qs.model.objects.filter(path__in=paths))


class SiteGeneralContentNode(DjangoNode[SiteGeneralContent]):
    class Meta:
        model = SiteGeneralContent
        fields = public_fields(SiteGeneralContent)


def get_admin_query():
    from actions.graphql_admin_schema import AdminQuery
    return AdminQuery


@sb.type
class Query(
    actions_schema.Query,
    indicators_schema.Query,
    orgs_schema.Query,
    pages_schema.Query,
    reports_schema.Query,
    datasets_schema.Query,
    search_schema.Query,
    graphene.ObjectType[Any],
):
    plan_organizations = graphene.List(
        graphene.NonNull(orgs_schema.OrganizationNode),
        plan=graphene.ID(),
        with_ancestors=graphene.Boolean(default_value=False),
        for_responsible_parties=graphene.Boolean(default_value=True),
        for_contact_persons=graphene.Boolean(default_value=False),
        include_related_plans=graphene.Boolean(default_value=False),
        required=False,
    )
    person = graphene.Field(people_schema.PersonNode, id=graphene.ID(required=True), plan=graphene.ID(required=True))
    me = graphene.Field(UserNode, required=False, description="The current user")

    @sb.field(description="Admin query namespace")
    @staticmethod
    def admin(root, info: gql.Info) -> Annotated[AdminQuery, sb.lazy('actions.graphql_admin_schema')]:
        user = user_or_none(info.context.user)
        if user is None or not user.is_superuser:
            raise PermissionError("Admin namespace requires authenticated access")
        return get_admin_query()()

    def resolve_plan_organizations(
        self, info: GQLInfo, plan: str | None, with_ancestors: bool, for_responsible_parties: bool, for_contact_persons: bool,
        include_related_plans: bool
    ) -> Iterable[Organization]:
        plan_obj: Plan | None = get_plan_from_context(info, plan)
        if plan_obj is None or not plan_obj.is_visible_for_user(info.context.user):
            return []

        if include_related_plans:
            plans = list(plan_obj.get_all_related_plans(inclusive=True).visible_for_user(info.context.user))
        else:
            plans = [plan_obj]

        visible_actions = Action.objects.qs.visible_for_user(info.context.user).filter(plan__in=plans)

        workflow_state = getattr(info.context.cache, 'query_workflow_state', None)
        some_plan_has_a_workflow = any(p.features.moderation_workflow is not None for p in plans)
        consider_responsible_parties_within_action_revisions = (
            workflow_state is not None and
            workflow_state != WorkflowStateEnum.PUBLISHED and
            some_plan_has_a_workflow
        )
        cache = None
        if consider_responsible_parties_within_action_revisions:
            info.context.cache.organization_action_count_cache = OrganizationActionCountCache(visible_actions)
            cache = info.context.cache.organization_action_count_cache

        qs = Organization.objects.qs.available_for_plans(plans)
        if plan is not None:
            # Note the weird behavior by Django: Q() is neither "true" nor "false".
            # For all x, Q() | x is equivalent to x, and Q() & x is also equivalent to x.
            query = Q()
            if for_responsible_parties:
                if consider_responsible_parties_within_action_revisions:
                    assert cache is not None
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
        if 'actionCount' in selections and not consider_responsible_parties_within_action_revisions:
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

    @staticmethod
    def resolve_person(_root, info: GQLInfo, id: str, plan: str | None = None) -> Person | None:
        user = user_or_none(info.context.user)
        plan_obj = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None
        qs = Person.objects.get_queryset().available_for_plan(plan_obj).visible_for_user(user, plan=plan_obj)
        return qs.filter(id=id).first()

    @staticmethod
    def resolve_me(_root, info: GQLInfo) -> User | None:
        return user_or_none(info.context.user)


@sb.type
class Mutation(
    actions_schema.Mutation,
    orgs_schema.Mutation,
    graphene.ObjectType[Any],
):
    create_user_feedback = feedback_schema.UserFeedbackMutation.Field()


@sb.type
class WatchTestModeMutations:
    @sb.field
    def test_mode(self) -> users_schema.TestMode:
        from django.conf import settings

        if not test_mode_enabled() and not settings.ENABLE_TEST_MODE:
            raise PermissionError('Test mode is not enabled')
        return users_schema.TestMode()


@sb.directive(
    locations=[DirectiveLocation.MUTATION],
    name='auth',
    description="Provide authentication data",
)
def auth_directive(info: gql.Info, uuid: str, token: str):  # pyright: ignore[reportUnusedParameter]
    return

graphene_enum_type = graphene.types.schema.TypeMap.create_enum(WorkflowStateGrapheneEnum)


class WorkflowStateDirective(GraphQLDirective):
    def __init__(self):
        super().__init__(
            name='workflow',
            description=(
                "Let the client request retrieving approved/unapproved "
                "drafts or published versions of plan data (currently individual actions). "
                "The actual response is dependent on user access rights, for example "
                "a published version is always returned to unauthenticated users "
                "or when no draft exists."
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


@sb.input(name='InstanceContext')
class InstanceContextInput:
    hostname: str | None
    identifier: sb.ID | None
    locale: str | None


@sb.directive(
    locations=[DirectiveLocation.QUERY, DirectiveLocation.MUTATION],
    name='context',
    description="Paths instance context, including the selected locale",
)
def context_directive(info: gql.Info, input: InstanceContextInput):  # pyright: ignore[reportUnusedParameter]
    return


@sb.directive(
    locations=[DirectiveLocation.QUERY],
    name='workflow',
    description=(
        "Let the client request retrieving approved/unapproved "
        "drafts or published versions of plan data (currently individual actions). "
        "The actual response is dependent on user access rights, for example "
        "a published version is always returned to unauthenticated users "
        "or when no draft exists."
    ),
)
def workflow_directive(
    info: gql.Info,  # pyright: ignore[reportUnusedParameter]
    state: Annotated[  # pyright: ignore[reportUnusedParameter]
        WorkflowStateEnum,
        sb.argument(
            description="State of content to show",
        )
    ] = WorkflowStateEnum.PUBLISHED
):
    return


class WatchSchema(UnifiedSchema):
    @copy_signature(StrawberrySchema.__init__)
    def __init__(self, *args, **kwargs):
        from .schema_context import (
            ActivatePlanContextExtension,
            DeterminePlanContextExtension,
            WatchAuthenticationExtension,
            WatchExecutionCacheExtension,
        )

        extensions = kwargs.pop('extensions', [])
        extensions.extend([
            LoggingTracingExtension(context_class=WatchGraphQLContext),
            DeterminePlanContextExtension,
            WatchExecutionCacheExtension,
            ActivatePlanContextExtension,
            WatchAuthenticationExtension,
        ])
        kwargs['extensions'] = extensions
        super().__init__(*args, **kwargs)


def _validate_type_registry(types: set[type]) -> None:
    registered_names = set()
    for type_ in types:
        meta = get_graphene_meta(type_)
        if meta is not None:
            name = meta.name
        elif has_object_definition(type_):
            name = type_.__strawberry_definition__.name
        else:
            raise TypeError(f"Type {type_} is not a valid Strawberry nor a Graphene type")
        if name in registered_names:
            raise ValueError(f"Type {type_} has name {name} which is already registered")
        registered_names.add(name)


Subscription = merge_types('Subscription', (actions_schema.Subscription,))


def generate_strawberry_schema() -> sb.Schema:
    from kausal_common.graphene.registry import registry as graphene_registry
    from kausal_common.strawberry.registry import strawberry_types

    all_types = set(strawberry_types)
    all_types.update(list(grapple_registry.models.values()))
    all_types.update(graphene_registry.get_list())

    _validate_type_registry(all_types)

    from django.conf import settings

    mutation_types: list[type] = [Mutation]
    if test_mode_enabled() or settings.ENABLE_TEST_MODE:
        mutation_types.append(WatchTestModeMutations)
    FinalMutation = merge_types('Mutation', tuple(mutation_types))

    schema = WatchSchema(
        query=Query,
        mutation=FinalMutation,
        subscription=Subscription,
        types=all_types,
        directives=[context_directive, workflow_directive, auth_directive],
    )
    return schema


schema = generate_strawberry_schema()
# We need a separate schema instance for async operations due to
# some weird behavior in the GraphQL MiddlewareManager.
async_schema = generate_strawberry_schema()
