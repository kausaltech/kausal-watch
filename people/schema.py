import graphene
from django.forms import ModelForm

from aplans.graphql_helpers import UpdateModelInstanceMutation
from aplans.graphql_types import DjangoNode, register_django_node
from .models import Person


@register_django_node
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


class PersonForm(ModelForm):
    # TODO: Eventually we will want to allow updating things other than organization
    class Meta:
        model = Person
        fields = ['organization']


class UpdatePersonMutation(UpdateModelInstanceMutation):
    class Meta:
        form_class = PersonForm


class Mutation(graphene.ObjectType):
    update_person = UpdatePersonMutation.Field()
