from __future__ import annotations

import typing

from rest_framework import exceptions, serializers

from actions.models import Plan

if typing.TYPE_CHECKING:
    from aplans.utils import PlanRelatedModel


def get_default_plan() -> Plan:
    return Plan.objects.get_queryset().live()[0]


class PlanRelatedModelSerializer[Model: PlanRelatedModel](serializers.ModelSerializer[Model]):
    plan: Plan

    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan', None)
        if self.plan:
            super().__init__(*args, **kwargs)
            return

        context = kwargs.get('context')
        if context is None:
            self.plan = get_default_plan()
            super().__init__(*args, **kwargs)
            return

        view = context['view']

        if getattr(view, 'swagger_fake_view', False):
            # Called during schema generation
            assert 'plan_pk' not in view.kwargs
            self.plan = get_default_plan()
            super().__init__(*args, **kwargs)
            return

        plan_pk = view.kwargs['plan_pk']
        plan = Plan.objects.filter(pk=plan_pk).prefetch_related('category_types').first()
        if plan is None:
            raise exceptions.NotFound('Plan not found')

        self.plan = plan
        super().__init__(*args, **kwargs)
