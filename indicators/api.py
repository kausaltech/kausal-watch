from plotly.graph_objs import Figure
from plotly.exceptions import PlotlyError
from rest_framework import viewsets, permissions
from rest_framework_json_api import serializers
import django_filters as filters
from .models import (
    Unit, Indicator, IndicatorEstimate, IndicatorGraph, RelatedIndicator, ActionIndicator,
    IndicatorLevel
)
from actions.models import Plan
from aplans.utils import register_view_helper


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
    permission_classes = (permissions.AllowAny,)


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

    prefetch_for_includes = {
        '__all__': [
            'levels', 'levels__plan', 'categories',
        ]
    }
    filterset_class = IndicatorFilter


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
