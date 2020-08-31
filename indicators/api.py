import aniso8601
import pytz
from datetime import datetime
from plotly.graph_objs import Figure
from plotly.exceptions import PlotlyError
from rest_framework import viewsets, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from django.db import transaction
from django.conf import settings
import django_filters as filters
from sentry_sdk import push_scope, capture_exception

from .models import (
    Unit, Indicator, IndicatorGraph, RelatedIndicator, ActionIndicator,
    IndicatorLevel, IndicatorValue
)
from actions.models import Plan
from aplans.utils import register_view_helper


LOCAL_TZ = pytz.timezone(settings.TIME_ZONE)


all_views = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class UnitSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Unit
        fields = ('name', 'verbose_name')


@register_view
class UnitViewSet(viewsets.ModelViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer


class IndicatorGraphSerializer(serializers.HyperlinkedModelSerializer):
    def validate_data(self, value):
        ALLOWED_KEYS = {'data', 'layout', 'frames'}
        if not isinstance(value, dict):
            raise serializers.ValidationError("Expecting JSON object")
        if not set(value.keys()).issubset(ALLOWED_KEYS):
            keys = ['"%s"' % x for x in ALLOWED_KEYS]
            raise serializers.ValidationError("Only allowed keys are: %s" % ', '.join(keys))

        try:
            figure = Figure(**value).to_dict()
        except (PlotlyError, ValueError) as err:
            with push_scope() as scope:
                scope.set_extra('plotly_json', value)
                scope.level = 'warning'
                capture_exception(err)
            raise serializers.ValidationError("Invalid Plotly object received:\n\n{0}".format(err))
        if not figure['data']:
            raise serializers.ValidationError("No Plotly data given in data.data")
        return value

    def create(self, validated_data):
        ret = super().create(validated_data)
        ret.indicator.latest_graph = ret
        ret.indicator.save(update_fields=['latest_graph'])
        return ret

    def update(self, instance, validated_data):
        ret = super().update(instance, validated_data)
        ret.indicator.latest_graph = ret
        ret.indicator.save(update_fields=['latest_graph'])
        return ret

    class Meta:
        model = IndicatorGraph
        fields = ('indicator', 'data', 'created_at')


@register_view
class IndicatorGraphViewSet(viewsets.ModelViewSet):
    queryset = IndicatorGraph.objects.all()
    serializer_class = IndicatorGraphSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)


class IndicatorLevelSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = IndicatorLevel
        fields = ('plan', 'indicator', 'level')


@register_view
class IndicatorLevelViewSet(viewsets.ModelViewSet):
    queryset = IndicatorLevel.objects.all()
    serializer_class = IndicatorLevelSerializer


class IndicatorSerializer(serializers.HyperlinkedModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True)

    included_serializers = {
        'plans': 'actions.api.PlanSerializer',
        'levels': IndicatorLevelSerializer,
        'categories': 'actions.api.CategorySerializer',
        'unit': UnitSerializer,
        'latest_graph': IndicatorGraphSerializer,
        'related_effects': 'indicators.api.RelatedIndicatorSerializer',
        'related_causes': 'indicators.api.RelatedIndicatorSerializer',
        'actions': 'actions.api.ActionSerializer',
    }

    class Meta:
        model = Indicator
        fields = (
            'name', 'unit', 'unit_name', 'levels', 'plans', 'description', 'categories',
            'time_resolution', 'latest_graph', 'actions',
            'related_effects', 'related_causes', 'updated_at',
        )


class IndicatorFilter(filters.FilterSet):
    plans = filters.ModelMultipleChoiceFilter(
        field_name='plans__identifier', to_field_name='identifier',
        queryset=Plan.objects
    )

    class Meta:
        model = Indicator
        fields = ('plans', 'identifier')


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
                print(obj, obj.id)
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


@register_view
class IndicatorViewSet(viewsets.ModelViewSet):
    queryset = Indicator.objects.all().select_related('unit')
    serializer_class = IndicatorSerializer
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)

    prefetch_for_includes = {
        '__all__': [
            'levels', 'levels__plan', 'categories',
        ]
    }
    filterset_class = IndicatorFilter

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


class RelatedIndicatorSerializer(serializers.HyperlinkedModelSerializer):
    included_serializers = {
        'causal_indicator': IndicatorSerializer,
        'effect_indicator': IndicatorSerializer,
    }

    class Meta:
        model = RelatedIndicator
        fields = '__all__'


@register_view
class RelatedIndicatorViewSet(viewsets.ModelViewSet):
    queryset = RelatedIndicator.objects.all()
    serializer_class = RelatedIndicatorSerializer


class ActionIndicatorSerializer(serializers.HyperlinkedModelSerializer):
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
