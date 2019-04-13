import aniso8601
import pytz

from datetime import datetime
from plotly.graph_objs import Figure
from plotly.exceptions import PlotlyError
from rest_framework import viewsets, permissions
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework_json_api import serializers
from django.conf import settings
import django_filters as filters
from .models import (
    Unit, Indicator, IndicatorEstimate, IndicatorGraph, RelatedIndicator, ActionIndicator,
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
        'estimates': 'indicators.api.IndicatorEstimateSerializer',
        'latest_graph': IndicatorGraphSerializer,
        'related_effects': 'indicators.api.RelatedIndicatorSerializer',
        'related_causes': 'indicators.api.RelatedIndicatorSerializer',
        'actions': 'actions.api.ActionSerializer',
    }

    class Meta:
        model = Indicator
        fields = (
            'name', 'unit', 'unit_name', 'levels', 'plans', 'description', 'categories',
            'time_resolution', 'estimates', 'latest_graph', 'actions',
            'related_effects', 'related_causes', 'updated_at',
        )


class IndicatorFilter(filters.FilterSet):
    plans = filters.ModelMultipleChoiceFilter(
        field_name='plans__identifier', to_field_name='identifier',
        queryset=Plan.objects
    )

    class Meta:
        model = Indicator
        fields = ('plans',)


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
        indicator = Indicator.objects.get(pk=pk)
        resp = []
        for i in range(100):
            resp.append(dict(time=now + timedelta(seconds=i), value=float(i)))
        return Response(resp)

    @values.mapping.post
    def update_values(self, request, pk=None):
        indicator = Indicator.objects.get(pk=pk)
        data = request.data['data']
        min_date = max_date = None
        values = []
        for sample in data:
            time = sample.get('time', '')
            try:
                date = aniso8601.parse_date(time)
            except ValueError as e:
                raise ValidationError("You must give 'time' in ISO 8601 format (YYYY-mm-dd)")

            if indicator.time_resolution == 'year':
                if date.day != 1 or date.month != 1:
                    raise ValidationError("Indicator has a yearly resolution, so '%s' must be '%d-01-01" % (time, date.year))
            elif indicator.time_resolution == 'month':
                if date.day != 1:
                    raise ValidationError("Indicator has a monthly resolution, so '%s' must be '%d-%02d-01" % (time, date.year, date.month))

            try:
                value = float(sample.get('value'))
            except TypeError:
                raise ValidationError("You must give 'value' as a floating point number")

            date = LOCAL_TZ.localize(datetime.combine(date, datetime.min.time()))
            if min_date is None or date < min_date:
                min_date = date
            if max_date is None or date > max_date:
                max_date = date
            values.append(IndicatorValue(indicator=indicator, time=date, value=value))

        dates = {}
        for value in values:
            date = value.time.date()
            if date in dates:
                raise ValidationError("Duplicate 'time' entry: %s" % (date.isoformat()))
            dates[date] = True

        n_deleted, _ = indicator.values.filter(time__gte=min_date, time__lte=max_date).delete()
        created = IndicatorValue.objects.bulk_create(values)

        latest_value = indicator.values.latest()
        if indicator.latest_value_id != latest_value.id:
            indicator.latest_value = latest_value
            indicator.save(update_fields=['latest_value'])

        return Response(dict(deleted=n_deleted, created=len(created)))


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


class IndicatorEstimateSerializer(serializers.HyperlinkedModelSerializer):
    scenario_identifier = serializers.CharField(source='scenario.identifier', read_only=True)
    included_serializers = {
        'indicator': IndicatorSerializer,
        'scenario': 'actions.api.ScenarioSerializer',
    }

    class Meta:
        model = IndicatorEstimate
        exclude = ('updated_by',)


@register_view
class IndicatorEstimateViewSet(viewsets.ModelViewSet):
    queryset = IndicatorEstimate.objects.all().select_related('scenario')
    serializer_class = IndicatorEstimateSerializer
