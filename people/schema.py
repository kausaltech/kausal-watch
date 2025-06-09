import graphene
from django.forms import ModelForm

from aplans.graphql_helpers import UpdateModelInstanceMutation
from aplans.graphql_types import DjangoNode, get_plan_from_context, register_django_node

from .models import Person

from kausal_common.people.schema import PersonNode as BasePersonNode


@register_django_node
class PersonNode(BasePersonNode):
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
        plan = get_plan_from_context(info)
        if plan.features.contact_persons_show_picture:
            return self.get_avatar_url(request, size)
        return None


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
