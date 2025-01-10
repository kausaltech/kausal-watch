from typing import TYPE_CHECKING

import graphene
from graphene_django.forms.mutation import DjangoModelFormMutation

import graphene_django_optimizer as gql_optimizer

from actions.models.action import ActionQuerySet
from aplans import graphql_gis  # noqa
from aplans.graphql_helpers import (
    AdminButtonsMixin,
    CreateModelInstanceMutation,
    DeleteModelInstanceMutation,
    UpdateModelInstanceMutation,
)
from aplans.graphql_types import AuthenticatedUserNode, DjangoNode, GQLInfo, register_django_node
from aplans.utils import public_fields

from actions.models import Plan
from orgs.forms import NodeForm
from orgs.models import Organization, OrganizationClass

if TYPE_CHECKING:
    from actions.models.plan import PlanQuerySet


# This form is just used in the GraphQL schema, not in Wagtail. For Wagtail, a different form class is created in
# OrganizationEditHandler.get_form_class().
class OrganizationForm(NodeForm):
    class Meta:
        model = Organization
        fields = ['parent', 'name', 'classification', 'abbreviation', 'founding_date', 'dissolution_date']


@register_django_node
class OrganizationClassNode(DjangoNode):
    class Meta:
        model = OrganizationClass
        fields = public_fields(OrganizationClass)


@register_django_node
class OrganizationNode(AdminButtonsMixin, DjangoNode):
    ancestors = graphene.List(lambda: OrganizationNode)
    descendants = graphene.List(lambda: OrganizationNode)
    action_count = graphene.Int(description='Number of actions this organization is responsible for', required=True)
    contact_person_count = graphene.Int(
        description='Number of contact persons that are associated with this organization',
        required=True,
    )
    parent = graphene.Field(lambda: OrganizationNode, required=False)
    logo = graphene.Field('images.schema.ImageNode', parent_fallback=graphene.Boolean(default_value=False), required=False)
    plans_with_action_responsibilities = graphene.List(
        graphene.NonNull('actions.schema.PlanNode'), except_plan=graphene.ID(required=False), required=True,
    )

    @staticmethod
    def resolve_ancestors(root: Organization, info):
        return root.get_ancestors()

    @staticmethod
    def resolve_descendants(parent, info):
        return parent.get_descendants()

    @staticmethod
    @gql_optimizer.resolver_hints(
        only=tuple(),
    )
    def resolve_action_count(parent, info):
        cache = getattr(info.context, 'organization_action_count_cache', None)
        if cache is None:
            return getattr(parent, 'action_count', 0)
        return cache.get_action_count_for_organization(parent.id)

    @staticmethod
    @gql_optimizer.resolver_hints(
        only=tuple(),
    )
    def resolve_contact_person_count(parent, info):
        return getattr(parent, 'contact_person_count', 0)

    @gql_optimizer.resolver_hints(
        only=('path', 'depth'),
    )
    def resolve_parent(parent: Organization, info):
        return parent.get_parent()

    @gql_optimizer.resolver_hints(
        only=('logo',),
        select_related=('logo',),
    )
    def resolve_logo(self: Organization, info: GQLInfo, parent_fallback=False):
        if self.logo is not None:
            return self.logo
        if parent_fallback:
            # Iterate through parents to find one that might have a logo
            org = self.get_parent()
            while org is not None:
                if org.logo is not None:
                    return org.logo
                org = org.get_parent()
        return None

    @staticmethod
    def resolve_plans_with_action_responsibilities(
        root: Organization, info: GQLInfo, except_plan: str | None = None,
    ):
        qs = Plan.objects.qs.filter(
            id__in=root.responsible_for_actions.values_list('plan'),
        )
        qs = qs.live()
        if except_plan:
            qs = qs.exclude(identifier=except_plan)
        return qs

    class Meta:
        model = Organization
        fields = [
            'id', 'abbreviation', 'name', 'description', 'url', 'email', 'classification', 'distinct_name', 'location',
        ]


class Query:
    organization = graphene.Field(OrganizationNode, id=graphene.ID(required=True))

    @staticmethod
    def resolve_organization(root, info, id):
        return Organization.objects.get(id=id)


class CreateOrganizationMutation(CreateModelInstanceMutation):
    class Meta:
        form_class = OrganizationForm


class UpdateOrganizationMutation(UpdateModelInstanceMutation):
    class Meta:
        form_class = OrganizationForm


class DeleteOrganizationMutation(DeleteModelInstanceMutation):
    class Meta:
        model = Organization


class Mutation(graphene.ObjectType):
    create_organization = CreateOrganizationMutation.Field()
    update_organization = UpdateOrganizationMutation.Field()
    delete_organization = DeleteOrganizationMutation.Field()
