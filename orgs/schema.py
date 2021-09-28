import graphene
import graphene_django_optimizer as gql_optimizer
from aplans.graphql_types import DjangoNode, register_django_node
from aplans.utils import public_fields
from graphene_django.forms.mutation import DjangoModelFormMutation

from orgs.models import Organization, OrganizationClass
from orgs.wagtail_hooks import OrganizationForm


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

    @staticmethod
    def resolve_parent(parent, info):
        return parent.get_parent()

    class Meta:
        model = Organization
        fields = [
            'id', 'abbreviation', 'name', 'classification', 'distinct_name',
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


class CreateOrganizationMutation(DjangoModelFormMutation):
    class Meta:
        form_class = OrganizationForm
        # Exclude `id`, otherwise we could change an existing organization by specifying an ID
        exclude_fields = ['id']


class UpdateOrganizationMutation(DjangoModelFormMutation):
    class Meta:
        form_class = OrganizationForm

    @classmethod
    def perform_mutate(cls, form, info):
        if form.instance.id is None:
            raise ValueError("ID not specified")
        return super().perform_mutate(form, info)


class DeleteOrganizationMutation(graphene.Mutation):
    class Arguments:
        id = graphene.ID()

    ok = graphene.Boolean()

    @classmethod
    def mutate(cls, root, info, id):
        obj = Organization.objects.get(pk=id)
        obj.delete()
        return cls(ok=True)


class Mutation(graphene.ObjectType):
    create_organization = CreateOrganizationMutation.Field()
    update_organization = UpdateOrganizationMutation.Field()
    delete_organization = DeleteOrganizationMutation.Field()
