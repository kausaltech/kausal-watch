from __future__ import annotations
import typing

from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import response, status, viewsets, exceptions, serializers
from rest_framework.exceptions import ValidationError

from actions.models import Plan
from aplans.types import WatchAPIRequest

if typing.TYPE_CHECKING:
    from django.db.models import QuerySet


class BulkListSerializer(serializers.ListSerializer):
    child: serializers.ModelSerializer
    instance: typing.Optional[QuerySet]
    update_lookup_field = 'id'

    def to_internal_value(self, data):
        id_attr = self.update_lookup_field
        errors = []
        qs = self.instance
        obj_ids = set()
        for item in data:
            obj_id = item.get(id_attr)
            if obj_id:
                if qs is None:
                    errors.append({id_attr: "Must not set attribute"})
                    continue
                obj_ids.add(obj_id)
            else:
                if qs is not None:
                    errors.append({id_attr: "Attribute missing"})
                    continue
        if any(errors):
            raise ValidationError(errors)

        if qs is not None:
            objs_by_id = {}
            self.obj_ids = []
            qs = qs.filter(**{'%s__in' % id_attr: obj_ids})
            for obj in qs:
                objs_by_id[getattr(obj, id_attr)] = obj
            seen_ids = set()
            for idx, item in enumerate(data):
                obj_id = item[id_attr]
                self.obj_ids.append(obj_id)
                if obj_id not in objs_by_id:
                    errors[idx] = {id_attr: "Unable to find object"}
                    continue
                if obj_id in seen_ids:
                    errors[idx] = {id_attr: "Duplicate value"}
                    continue
                seen_ids.add(obj_id)
            self.objs_by_id = objs_by_id

        if any(errors):
            raise ValidationError(errors)

        return super().to_internal_value(data)

    def update(self, queryset, all_validated_data):
        updated_data = []
        for obj_id, obj_data in zip(self.obj_ids, all_validated_data):
            obj = self.objs_by_id[obj_id]
            updated_data.append(self.child.update(obj, obj_data))
        return updated_data

    def create(self, validated_data):
        result = [self.child.create(attrs) for attrs in validated_data]
        return result


class BulkModelViewSet(viewsets.ModelViewSet):
    request: WatchAPIRequest

    def bulk_create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return response.Response(
            serializer.data, status=status.HTTP_201_CREATED, headers=headers
        )

    def bulk_update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        serializer = self.get_serializer(
            self.filter_queryset(self.get_queryset()),
            data=request.data,
            many=True,
            partial=partial
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
                plan_pk = view.kwargs['plan_pk']
                plan = Plan.objects.filter(pk=plan_pk).prefetch_related('category_types').first()
                if plan is None:
                    raise exceptions.NotFound('Plan not found')
                self.plan = plan
            else:
                # Probably used for schema generation
                self.plan = get_default_plan()

        super().__init__(*args, **kwargs)


class ProtectedError(exceptions.APIException):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_detail = _('Cannot delete instance because other objects reference it.')
    default_code = 'protected_error'


class HandleProtectedErrorMixin:
    """Mixin for viewsets that use DRF's DestroyModelMixin to handle ProtectedError gracefully."""
    def perform_destroy(self, instance):
        try:
            super().perform_destroy(instance)
        except models.ProtectedError as e:
            raise ProtectedError(detail=str(e))
