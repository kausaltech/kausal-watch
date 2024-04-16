import typing

import graphene
import graphene_django_optimizer as gql_optimizer

from django.db.models import Count, Q
from graphql.error import GraphQLError
from graphql import DirectiveLocation
from graphql.type import (
    GraphQLArgument, GraphQLDirective, GraphQLNonNull, GraphQLString, specified_directives
)
from grapple.registry import registry as grapple_registry

from actions.models.action import Action

from . import graphql_gis  # noqa

from actions import schema as actions_schema
from actions.models import Plan
from aplans.utils import public_fields
from aplans.graphql_types import WorkflowStateGrapheneEnum
from admin_site.wagtail import PlanRelatedPermissionHelper
from content.models import SiteGeneralContent
from feedback import schema as feedback_schema
from indicators import schema as indicators_schema
from orgs import schema as orgs_schema
from orgs.models import Organization
from pages import schema as pages_schema
from people import schema as people_schema
from people.models import Person
from reports import schema as reports_schema
from search import schema as search_schema

from .graphql_helpers import get_fields
from .graphql_types import DjangoNode, GQLInfo, get_plan_from_context, graphene_registry, WorkflowStateEnum, register_graphene_node


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
    search_schema.Query,
    graphene.ObjectType
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
        include_related_plans: bool, **kwargs
    ):
        plan_obj: Plan | None = get_plan_from_context(info, plan)
        if plan_obj is None:
            return None

        if include_related_plans:
            plans = list(plan_obj.get_all_related_plans(inclusive=True))
        else:
            plans = [plan_obj]

        visible_actions = Action.objects.visible_for_user(info.context.user).filter(plan__in=plans)
        qs = Organization.objects.available_for_plans(plans)
        if plan is not None:
            # Note the weird behavior by Django: Q() is neither "true" nor "false".
            # For all x, Q() | x is equivalent to x, and Q() & x is also equivalent to x.
            query = Q()
            if for_responsible_parties:
                query |= Q(responsible_actions__action__in=visible_actions)
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
            annotate_filter = Q(responsible_actions__action__in=visible_actions)
            qs = qs.annotate(action_count=Count(
                'responsible_actions__action', distinct=True, filter=annotate_filter
            ))
        if 'contactPersonCount' in selections and plan_obj.features.public_contact_persons:
            # FIXME: Check visibility of related plans, too
            annotate_filter = Q(people__contact_for_actions__in=visible_actions)
            qs = qs.annotate(contact_person_count=Count(
                'people', distinct=True, filter=annotate_filter
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
    graphene.ObjectType
):
    create_user_feedback = feedback_schema.UserFeedbackMutation.Field()


class LocaleDirective(GraphQLDirective):
    def __init__(self):
        super().__init__(
            name='locale',
            description='Select locale in which to return data',
            args={
                'lang': GraphQLArgument(
                    type_=GraphQLNonNull(GraphQLString),
                    description="Language code of the locale to use"
                ),
            },
            locations=[DirectiveLocation.QUERY]
        )


class AuthDirective(GraphQLDirective):
    def __init__(self):
        super().__init__(
            name='auth',
            description="Provide authentication data",
            args={
                'uuid': GraphQLArgument(
                    type_=GraphQLNonNull(GraphQLString),
                    description="User UUID"
                ),
                'token': GraphQLArgument(
                    type_=GraphQLNonNull(GraphQLString),
                    description="Authentication token"
                ),
            },
            locations=[DirectiveLocation.MUTATION]
        )

graphene_enum_type = graphene.types.schema.TypeMap.create_enum(WorkflowStateGrapheneEnum)


class WorkflowStateDirective(GraphQLDirective):
    def __init__(self):
        super().__init__(
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
                    default_value='published'
                )
            },
            locations=[DirectiveLocation.QUERY]
        )


schema = graphene.Schema(
    query=Query,
    mutation=Mutation,
    directives=specified_directives + (LocaleDirective(), AuthDirective(), WorkflowStateDirective()),
    types=graphene_registry + list(grapple_registry.models.values()),
)
