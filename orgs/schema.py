import graphene
from aplans.graphql_types import DjangoNode, register_django_node
from aplans.utils import public_fields
from graphene_django.forms.mutation import DjangoModelFormMutation

from orgs.models import Organization
from orgs.wagtail_hooks import OrganizationForm


@register_django_node
class NewOrganizationNode(DjangoNode):
    # TODO: Replace legacy OrganizationNode with this one eventually
    class Meta:
        model = Organization
        fields = public_fields(Organization, add_fields=['parent'])

    parent = graphene.Field(lambda: NewOrganizationNode)

    @staticmethod
    def resolve_parent(root, info):
        return root.get_parent()


class Query:
    organization = graphene.Field(NewOrganizationNode, id=graphene.ID(required=True))
    all_organizations = graphene.List(NewOrganizationNode)

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
