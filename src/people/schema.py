from __future__ import annotations

import graphene
from django.forms import ModelForm

from kausal_common.people.schema import PersonNode as BasePersonNode

from aplans.graphql_types import DjangoNode, get_plan_from_context, register_django_node

from .models import Person


@register_django_node
class PersonNode(BasePersonNode, DjangoNode[Person]):
    avatar_url = graphene.String(size=graphene.String())

    class Meta:
        model = Person
        fields = [
            'id',
            'first_name',
            'last_name',
            'title',
            'email',
            'organization',
        ]

    @staticmethod
    def resolve_avatar_url(root: Person, info, size: str | None = None) -> str | None:
        request = info.context
        if not request:
            return None
        plan = get_plan_from_context(info)
        if plan.features.contact_persons_show_picture:
            return root.get_avatar_url(request, size)
        return None


class PersonForm(ModelForm[Person]):
    # TODO: Eventually we will want to allow updating things other than organization
    class Meta:
        model = Person
        fields = ['organization']
