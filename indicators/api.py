from rest_framework import viewsets
from rest_framework_json_api import serializers
from .models import (
    Indicator, IndicatorEstimate
)
from aplans.utils import register_view_helper


all_views = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class IndicatorSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Indicator
        fields = ('name', 'identifier')


@register_view
class IndicatorViewSet(viewsets.ModelViewSet):
    queryset = Indicator.objects.all()
    serializer_class = IndicatorSerializer
