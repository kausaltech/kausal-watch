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


class BulkModelViewSet(viewsets.ModelViewSet):
    request: WatchAPIRequest

    def bulk_create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return response.Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers,
        )

    def bulk_update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(
            self.filter_queryset(self.get_queryset()),
            data=request.data,
            many=True,
            partial=partial,
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return response.Response(serializer.data)

    def partial_bulk_update(self, request, *args, **kwargs):
        kwargs['partial'] = True
        return self.bulk_update(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        if isinstance(request.data, list):
            return self.bulk_create(request, *args, **kwargs)
        return super().create(request, *args, **kwargs)


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
