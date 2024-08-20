from django import forms
from graphene_django.forms.mutation import DjangoModelFormMutation

from aplans.graphql_types import DjangoObjectType
from aplans.utils import public_fields

from actions.models import Plan

from .models import UserFeedback


class UserFeedbackForm(forms.ModelForm):
    plan = forms.ModelChoiceField(queryset=Plan.objects.all(), to_field_name='identifier')
    class Meta:
        model = UserFeedback
        fields = ('plan', 'type', 'action', 'category', 'name', 'email', 'comment', 'url', 'additional_fields')


class UserFeedbackNode(DjangoObjectType):
    class Meta:
        model = UserFeedback
        fields = public_fields(UserFeedback)


class UserFeedbackMutation(DjangoModelFormMutation):
    class Meta:
        form_class = UserFeedbackForm
        input_field_name = 'data'
        return_field_name = 'feedback'
