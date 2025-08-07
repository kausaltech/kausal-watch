from __future__ import annotations

import typing

from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, response, serializers, status, viewsets
from rest_framework.exceptions import ValidationError

from actions.models import Plan

if typing.TYPE_CHECKING:
    from django.db.models import QuerySet

    from aplans.types import WatchAPIRequest


def get_default_plan() -> Plan:
    return Plan.objects.live().first()


class PlanRelatedModelSerializer(serializers.ModelSerializer):
    plan: Plan

    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan', None)
        if not self.plan:
            context = kwargs.get('context')
            if context is not None:
                view = context['view']
                if getattr(view, 'swagger_fake_view', False):
                    # Called during schema generation
                    assert 'plan_pk' not in view.kwargs
                    self.plan = get_default_plan()
                else:
                    plan_pk = view.kwargs['plan_pk']
                    plan = Plan.objects.filter(pk=plan_pk).prefetch_related('category_types').first()
                    if plan is None:
                        raise exceptions.NotFound('Plan not found')
                    self.plan = plan
            else:
                # Probably called during schema generation
                self.plan = get_default_plan()
        super().__init__(*args, **kwargs)
