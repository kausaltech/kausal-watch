import graphene
import graphene_django_optimizer as gql_optimizer

from django.db.models import Count, Q
from django_orghierarchy.models import Organization, OrganizationClass
from graphql.error import GraphQLError
from graphql.type import (
    DirectiveLocation, GraphQLArgument, GraphQLDirective, GraphQLNonNull, GraphQLString, specified_directives
)
from grapple.registry import registry as grapple_registry

from aplans.utils import public_fields
from content.models import SiteGeneralContent
from actions import schema as actions_schema
from feedback import schema as feedback_schema
from indicators import schema as indicators_schema
from orgs import schema as orgs_schema
from pages import schema as pages_schema
from people.models import Person

from .graphql_helpers import get_fields
from .graphql_types import DjangoNode, get_plan_from_context


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
        fields = [
            'id', 'first_name', 'last_name', 'title', 'email', 'organization',
        ]

    def resolve_avatar_url(self, info, size=None):
        request = info.context
        if not request:
            return None
        return self.get_avatar_url(request, size)


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
        fields = [
            'id', 'abbreviation', 'parent', 'name', 'classification', 'distinct_name',
        ]


class SiteGeneralContentNode(DjangoNode):
    class Meta:
        model = SiteGeneralContent
        fields = public_fields(SiteGeneralContent)


class Query(
    actions_schema.Query,
    indicators_schema.Query,
    orgs_schema.Query,
    pages_schema.Query,
    graphene.ObjectType
):
    plan_organizations = graphene.List(
        OrganizationNode, plan=graphene.ID(),
        with_ancestors=graphene.Boolean(default_value=False),
        for_responsible_parties=graphene.Boolean(default_value=True),
        for_contact_persons=graphene.Boolean(default_value=False),
    )
    person = graphene.Field(PersonNode, id=graphene.ID(required=True))

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

    def resolve_person(self, info, **kwargs):
        qs = Person.objects.all()
        obj_id = kwargs.get('id')
        qs = qs.filter(id=obj_id)
        try:
            obj = qs.get()
        except Person.DoesNotExist:
            return None

        return obj


class Mutation(orgs_schema.Mutation, graphene.ObjectType):
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
