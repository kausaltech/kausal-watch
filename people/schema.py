import graphene
from django.forms import ModelForm

from aplans.graphql_helpers import UpdateModelInstanceMutation
from .models import Person


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
