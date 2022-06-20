import graphene
import graphene_django_optimizer as gql_optimizer
from aplans.graphql_helpers import CreateModelInstanceMutation, DeleteModelInstanceMutation, UpdateModelInstanceMutation
from aplans.graphql_types import AuthenticatedUserNode, DjangoNode, GQLInfo, register_django_node
from graphene_django.forms.mutation import DjangoModelFormMutation

from actions.models import Plan
from orgs.forms import NodeForm
from orgs.models import Organization, OrganizationClass


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


@register_django_node
class OrganizationNode(DjangoNode):
    ancestors = graphene.List(lambda: OrganizationNode)
    action_count = graphene.Int(description='Number of actions this organization is responsible for')
    contact_person_count = graphene.Int(
        description='Number of contact persons that are associated with this organization'
    )
    parent = graphene.Field(lambda: OrganizationNode, required=False)
    logo = graphene.Field('images.schema.ImageNode', parent_fallback=graphene.Boolean(default_value=False), required=False)
    plans_with_action_responsibilities = graphene.List('actions.schema.PlanNode')

    @staticmethod
    def resolve_ancestors(parent, info):
        return parent.get_ancestors()

    @staticmethod
    @gql_optimizer.resolver_hints(
        only=tuple(),
    )
    def resolve_action_count(parent, info):
        return getattr(parent, 'action_count', None)

    @staticmethod
    @gql_optimizer.resolver_hints(
        only=tuple(),
    )
    def resolve_contact_person_count(parent, info):
        return getattr(parent, 'contact_person_count', None)

    @gql_optimizer.resolver_hints(
        only=('path', 'depth')
    )
    def resolve_parent(parent: Organization, info):
        return parent.get_parent()

    @gql_optimizer.resolver_hints(
        only=('logo',)
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

    def resolve_plans_with_action_responsibilities(root, info):
        return Plan.objects.filter(id__in=root.responsible_for_actions.values_list('plan'))

    class Meta:
        model = Organization
        fields = [
            'id', 'abbreviation', 'name', 'description', 'url', 'classification', 'distinct_name', 'location',
        ]


class Query:
    organization = graphene.Field(OrganizationNode, id=graphene.ID(required=True))
    all_organizations = graphene.List(OrganizationNode)

    @staticmethod
    def resolve_organization(root, info, id):
        return Organization.objects.get(id=id)

    @staticmethod
    def resolve_all_organizations(root, info):
        return Organization.objects.all()


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
