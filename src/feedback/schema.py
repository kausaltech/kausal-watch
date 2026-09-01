from __future__ import annotations

from typing import Self

from django import forms
from graphene_django import DjangoObjectType
from graphene_django.forms.mutation import DjangoModelFormMutation
from wagtail.log_actions import log

from aplans.utils import public_fields

from actions.models import Plan

from .models import UserFeedback


class UserFeedbackForm(forms.ModelForm[UserFeedback]):
    plan = forms.ModelChoiceField(queryset=Plan.objects.all(), to_field_name='identifier')

    class Meta:
        model = UserFeedback
        fields = (
            'plan',
            'type',
            'action',
            'category',
            'pledge',
            'name',
            'email',
            'comment',
            'url',
            'additional_fields',
            'page_id',
        )


class UserFeedbackNode(DjangoObjectType[UserFeedback]):
    class Meta:
        model = UserFeedback
        fields = public_fields(UserFeedback)


class UserFeedbackMutation(DjangoModelFormMutation):
    class Meta:
        form_class = UserFeedbackForm
        input_field_name = 'data'
        return_field_name = 'feedback'

    @classmethod
    def perform_mutate(cls, form, info) -> Self:
        mutation = super().perform_mutate(form, info)
        instance = mutation.feedback
        log(
            instance=instance,
            action='feedback.received',
            user=None,
        )
        return mutation
