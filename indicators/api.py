from datetime import datetime

import pytz
from django.conf import settings
from django.db import transaction

import django_filters as filters
from django_orghierarchy.models import Organization
from actions.models import Plan
from aplans.utils import register_view_helper
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from sentry_sdk import capture_exception, push_scope

from .models import ActionIndicator, Indicator, IndicatorLevel, IndicatorValue, RelatedIndicator, Unit

LOCAL_TZ = pytz.timezone(settings.TIME_ZONE)


all_views = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class UnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Unit
        fields = ('name', 'verbose_name')


@register_view
class UnitViewSet(viewsets.ModelViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer


class IndicatorLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicatorLevel
        fields = ('plan', 'level')


class RelatedIndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = RelatedIndicator
        fields = '__all__'


class IndicatorSerializer(serializers.ModelSerializer):
    unit = serializers.CharField(source='unit.name')
    related_effects = RelatedIndicatorSerializer(many=True, required=False)
    related_causes = RelatedIndicatorSerializer(many=True, required=False)
    levels = IndicatorLevelSerializer(many=True, required=False)
    organization = serializers.PrimaryKeyRelatedField(
        many=False, required=True, queryset=Organization.objects.filter(plans__isnull=False).distinct()
    )

    def validate(self, data):
        data = super().validate(data)
        org = data['organization']
        levels = data.get('levels', None)
        if levels:
            for level in levels:
                if level['plan'].organization != org:
                    raise ValidationError('Attempting to set indicator level for wrong plan')

        if Indicator.objects.filter(organization=org, name=data['name']).exists():
            raise ValidationError('Indicator with the same name already exists for organization')

        return data

    def validate_levels(self, levels):
        return levels

    def validate_organization(self, val):
        user = self.context['request'].user
        admin_orgs = user.get_adminable_organizations()
        if not user.is_superuser and val not in admin_orgs:
            raise ValidationError('No permission for organisation %s' % val.name)
        return val

    def validate_unit(self, val):
        try:
            unit = Unit.objects.get(name=val)
        except Unit.DoesNotExist:
            raise ValidationError('Unit does not exist')
        return unit

    def create(self, validated_data):
        unit = validated_data.pop('unit')['name']
        levels = validated_data.pop('levels', None)
        with transaction.atomic():
            obj = Indicator.objects.create(unit=unit, **validated_data)
            if levels:
                level_objs = [IndicatorLevel(indicator=obj, plan=x['plan'], level=x['level']) for x in levels]
                IndicatorLevel.objects.bulk_create(level_objs)
        return obj

    class Meta:
        model = Indicator
        fields = (
            'id', 'name', 'unit', 'levels', 'plans', 'description', 'categories',
            'time_resolution', 'actions', 'related_effects', 'related_causes', 'updated_at',
            'organization',
        )


class IndicatorFilter(filters.FilterSet):
    plans = filters.ModelMultipleChoiceFilter(
        field_name='plans__identifier', to_field_name='identifier',
        queryset=Plan.objects
    )
    organization = filters.ModelChoiceFilter(
        queryset=Organization.objects.filter(indicators__isnull=False).distinct()
    )

    class Meta:
        model = Indicator
        fields = ('plans', 'identifier', 'organization')


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
            n_deleted, _ = indicator.values.all().delete()

            for data in validated_data:
                categories = data.pop('categories', [])
                obj = IndicatorValue(indicator=indicator, **data)
                obj.save()
                if categories:
                    obj.categories.set(categories)
                created_objs.append(obj)

            if len(created_objs):
                latest_value_id = indicator.values.filter(categories__isnull=True).latest().id
            else:
                latest_value_id = None

            if indicator.latest_value_id != latest_value_id:
                indicator.latest_value_id = latest_value_id
                indicator.save(update_fields=['latest_value_id'])

            for plan in indicator.plans.all():
                plan.invalidate_cache()

        return created_objs


class IndicatorValueSerializer(serializers.ModelSerializer):
    def validate_date(self, date):
        indicator = self.context['indicator']
        if indicator.time_resolution == 'year':
            if date.day != 31 or date.month != 12:
                raise ValidationError("Indicator has a yearly resolution, so '%s' must be '%d-12-31" % (date, date.year))
        elif indicator.time_resolution == 'month':
            if date.day != 1:
                raise ValidationError("Indicator has a monthly resolution, so '%s' must be '%d-%02d-01" % (date, date.year, date.month))
        return date

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


@register_view
class IndicatorViewSet(viewsets.ModelViewSet):
    queryset = Indicator.objects.all().select_related('unit')
    serializer_class = IndicatorSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)

    filterset_class = IndicatorFilter

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

    @values.mapping.post
    def update_values(self, request, pk=None):
        indicator = Indicator.objects.prefetch_related(
            'dimensions', 'dimensions__dimension', 'dimensions__dimension__categories'
        ).get(pk=pk)
        serializer = IndicatorValueSerializer(data=request.data, many=True, context={'indicator': indicator})
        if serializer.is_valid():
            serializer.create(serializer.validated_data)
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response({})


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
