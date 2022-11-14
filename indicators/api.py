from datetime import datetime

import pytz
from django.conf import settings
from django.db import transaction

import django_filters as filters
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from sentry_sdk import capture_exception, push_scope

from .models import (
    ActionIndicator, Indicator, IndicatorLevel, IndicatorGoal, IndicatorValue, Quantity, RelatedIndicator, Unit
)
from actions.api import plan_router
from actions.models import Plan
from aplans.utils import register_view_helper
from orgs.models import Organization

LOCAL_TZ = pytz.timezone(settings.TIME_ZONE)


all_views = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class QuantitySerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='name_i18n')

    class Meta:
        model = Quantity
        fields = ('id', 'name')


@register_view
class QuantityViewSet(viewsets.ModelViewSet):
    queryset = Quantity.objects.all()
    serializer_class = QuantitySerializer


class UnitSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='name_i18n')

    class Meta:
        model = Unit
        fields = ('id', 'name', 'verbose_name')


@register_view
class UnitViewSet(viewsets.ModelViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer


class IndicatorLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicatorLevel
        fields = ('plan', 'level')


class RelatedCausalIndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = RelatedIndicator
        fields = ('causal_indicator', 'effect_type', 'confidence_level')


class RelatedEffectIndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = RelatedIndicator
        fields = ('effect_indicator', 'effect_type', 'confidence_level')


class IndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Indicator
        fields = (
            'id', 'name', 'quantity', 'unit', 'time_resolution', 'organization', 'updated_values_due_at'
        )

    def create(self, validated_data: dict):
        instance = super().create(validated_data)
        assert not instance.levels.exists()
        plan = self.context['request'].user.get_active_admin_plan()
        level = 'strategic'
        assert level in [v for v, _ in Indicator.LEVELS]
        instance.levels.create(plan=plan, level=level)
        return instance


class IndicatorFilter(filters.FilterSet):
    plans = filters.ModelMultipleChoiceFilter(
        field_name='plans__identifier', to_field_name='identifier',
        queryset=Plan.objects
    )

    class Meta:
        model = Indicator
        fields = ('plans', 'identifier', 'organization', 'name')


class IndicatorValueListSerializer(serializers.ListSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        indicator = self.context['indicator']

        dims = [x.dimension for x in indicator.dimensions.all()]
        cat_by_id = {}
        for dim in dims:
            for cat in dim.categories.all():
                cat_by_id[cat.id] = cat

        data_by_date = {}

        for sample in data:
            date = sample['date']
            categories = tuple(sorted([x.id for x in sample['categories']]))
            dd = data_by_date.setdefault(date, {})
            if categories in dd:
                raise ValidationError("duplicate categories for %s: %s" % (date, categories))
            dd[categories] = True

        for date, vals in data_by_date.items():
            if tuple() not in vals:
                raise ValidationError("no default value provided for %s" % date)

        return data

    def create(self, validated_data):
        indicator = self.context['indicator']
        created_objs = []

        with transaction.atomic():
            indicator.values.all().delete()
            indicator.latest_value = None

            for data in validated_data:
                categories = data.pop('categories', [])
                obj = IndicatorValue(indicator=indicator, **data)
                obj.save()
                if categories:
                    obj.categories.set(categories)
                created_objs.append(obj)

            indicator.handle_values_update()

            for plan in indicator.plans.all():
                plan.invalidate_cache()

        return created_objs


class IndicatorGoalListSerializer(serializers.ListSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        seen_dates = set()
        for sample in data:
            date = sample['date']
            if date in seen_dates:
                raise ValidationError("Duplicate date values")
            if 'value' not in sample or sample['value'] is None:
                raise ValidationError("Value is required")
            seen_dates.add(date)
        return data

    def create(self, validated_data):
        indicator = self.context['indicator']
        created_objs = []

        with transaction.atomic():
            indicator.goals.all().delete()

            for data in validated_data:
                obj = IndicatorGoal(indicator=indicator, **data)
                obj.save()
                created_objs.append(obj)

        return created_objs


class IndicatorDataPointMixin:
    def validate_date(self, date):
        indicator = self.context['indicator']
        if indicator.time_resolution == 'year':
            if date.day != 31 or date.month != 12:
                raise ValidationError("Indicator has a yearly resolution, so '%s' must be '%d-12-31" % (date, date.year))
        elif indicator.time_resolution == 'month':
            if date.day != 1:
                raise ValidationError("Indicator has a monthly resolution, so '%s' must be '%d-%02d-01" % (date, date.year, date.month))
        return date


class IndicatorValueSerializer(serializers.ModelSerializer, IndicatorDataPointMixin):

    def validate_categories(self, cats):
        indicator = self.context['indicator']

        dims = [x.dimension for x in indicator.dimensions.all()]
        cat_by_id = {}
        for dim in dims:
            for cat in dim.categories.all():
                cat_by_id[cat.id] = cat

        found_dims = set()
        for cat in cats:
            cat = cat_by_id.get(cat.id)
            if cat is None:
                raise ValidationError("category %d not found in indicator dimensions" % cat.id)
            if cat.dimension_id in found_dims:
                raise ValidationError("dimension already present for category %s" % cat.id)
            found_dims.add(cat.dimension_id)

        if len(found_dims) and len(found_dims) != len(dims):
            raise ValidationError("not all dimensions found for %s: %s" % (self.data['date'], [cat.id for cat in cats]))

        return cats

    class Meta:
        model = IndicatorValue
        fields = ['date', 'value', 'categories']
        list_serializer_class = IndicatorValueListSerializer


class IndicatorGoalSerializer(serializers.ModelSerializer, IndicatorDataPointMixin):
    def to_internal_value(self, data):
        data['indicator_id'] = self.context['indicator'].pk
        return data

    class Meta:
        model = IndicatorGoal
        list_serializer_class = IndicatorGoalListSerializer
        fields = ['date', 'value']


class IndicatorEditValuesPermission(permissions.DjangoObjectPermissions):
    def has_permission(self, request, view):
        perms = self.get_required_permissions(request.method, IndicatorValue)
        return request.user.has_perms(perms)

    def has_object_permission(self, request, view, obj):
        perms = self.get_required_object_permissions(request.method, IndicatorValue)
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        user = request.user
        if not user.has_perms(perms):
            return False
        return user.can_modify_indicator(obj)


class IndicatorViewSet(viewsets.ModelViewSet):
    serializer_class = IndicatorSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)

    filterset_class = IndicatorFilter

    def get_queryset(self):
        plan_pk = self.kwargs.get('plan_pk')
        if not plan_pk:
            return Indicator.objects.none()
        plan = Plan.objects.get(pk=plan_pk)
        return Indicator.objects.available_for_plan(plan)

    def get_permissions(self):
        if self.action == 'update_values':
            perms = [IndicatorEditValuesPermission]
        else:
            perms = list(self.permission_classes)
        return [perm() for perm in perms]

    def check_object_permission(self, request, obj):
        super().check_object_permissions(request, obj)
        user = request.user
        if obj is not None:
            if not user.can_modify_indicator(obj):
                self.permission_denied(
                    request,
                    message='No permission to modify indicator',
                    code='no_indicator_permission'
                )
        else:
            if not user.can_create_indicator(plan=None):
                self.permission_denied(
                    request,
                    message='No permission to modify indicator',
                    code='no_indicator_permission'
                )

    @action(detail=True, methods=['get'])
    def values(self, request, pk=None):
        indicator = self.get_object()
        objs = indicator.values.all().order_by('date').prefetch_related('categories')
        serializer = IndicatorValueSerializer(objs, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def goals(self, request, pk=None):
        indicator = Indicator.objects.get(pk=pk)
        resp = []
        for obj in indicator.goals.all().order_by('date'):
            resp.append(dict(date=obj.date, value=obj.value))
        return Response(resp)

    @goals.mapping.post
    def update_goals(self, request, plan_pk, pk):
        indicator = Indicator.objects.get(pk=pk)
        serializer = IndicatorGoalSerializer(data=request.data, many=True, context={'indicator': indicator})
        if serializer.is_valid():
            serializer.create(serializer.validated_data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({})

    @values.mapping.post
    def update_values(self, request, plan_pk, pk):
        indicator = Indicator.objects.prefetch_related(
            'dimensions', 'dimensions__dimension', 'dimensions__dimension__categories'
        ).get(pk=pk)
        serializer = IndicatorValueSerializer(data=request.data, many=True, context={'indicator': indicator})
        if serializer.is_valid():
            serializer.create(serializer.validated_data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response({})


plan_router.register('indicators', IndicatorViewSet, basename='indicator')


class ActionIndicatorSerializer(serializers.ModelSerializer):
    included_serializers = {
        'action': 'actions.api.ActionSerializer',
        'indicator': IndicatorSerializer,
    }

    class Meta:
        model = ActionIndicator
        fields = '__all__'


@register_view
class ActionIndicatorViewSet(viewsets.ModelViewSet):
    queryset = ActionIndicator.objects.all()
    serializer_class = ActionIndicatorSerializer
