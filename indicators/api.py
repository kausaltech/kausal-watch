from rest_framework import viewsets
from rest_framework_json_api import serializers
from .models import (
    Unit, Indicator, IndicatorEstimate
)
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


class IndicatorSerializer(serializers.HyperlinkedModelSerializer):
    unit_name = serializers.CharField(source='unit.name', read_only=True)

    included_serializers = {
        'plan': 'actions.api.PlanSerializer',
        'categories': 'actions.api.CategorySerializer',
        'unit': UnitSerializer,
        'estimates': 'indicators.api.IndicatorEstimateSerializer'
    }

    class Meta:
        model = Indicator
        fields = ('plan', 'name', 'unit', 'unit_name', 'description', 'categories', 'time_resolution')


@register_view
class IndicatorViewSet(viewsets.ModelViewSet):
    queryset = Indicator.objects.all().select_related('unit')
    serializer_class = IndicatorSerializer


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
