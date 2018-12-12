from rest_framework import viewsets
from rest_framework_json_api import serializers
from .models import (
    Plan, Action, ActionSchedule, Category, CategoryType, Scenario, ActionStatus,
    ActionTask
)
from aplans.utils import register_view_helper
from django_orghierarchy.models import Organization
from rest_framework_json_api import django_filters
from rest_framework_json_api.relations import ResourceRelatedField


all_views = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class PlanSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Plan
        fields = ('name', 'identifier')


@register_view
class PlanViewSet(viewsets.ModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer


class ActionScheduleSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = ActionSchedule
        fields = '__all__'


@register_view
class ActionScheduleViewSet(viewsets.ModelViewSet):
    queryset = ActionSchedule.objects.all()
    serializer_class = ActionScheduleSerializer


class ActionStatusSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = ActionStatus
        fields = '__all__'


@register_view
class ActionStatusViewSet(viewsets.ModelViewSet):
    queryset = ActionStatus.objects.all()
    serializer_class = ActionStatusSerializer


class CategoryTypeSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = CategoryType
        fields = '__all__'


@register_view
class CategoryTypeViewSet(viewsets.ModelViewSet):
    queryset = CategoryType.objects.all()
    serializer_class = CategoryTypeSerializer


class CategorySerializer(serializers.HyperlinkedModelSerializer):
    included_serializers = {
        'parent': 'actions.api.CategorySerializer',
    }

    class Meta:
        model = Category
        fields = '__all__'


@register_view
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class OrganizationSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Organization
        fields = ('id', 'name', 'abbreviation', 'parent')


@register_view
class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer


class ActionSerializer(serializers.HyperlinkedModelSerializer):
    included_serializers = {
        'plan': PlanSerializer,
        'schedule': ActionScheduleSerializer,
        'status': ActionStatusSerializer,
        'categories': CategorySerializer,
        'responsible_parties': OrganizationSerializer,
        'tasks': 'actions.api.ActionTaskSerializer',
        'indicators': 'indicators.api.IndicatorSerializer',
    }
    tasks = ResourceRelatedField(queryset=ActionTask.objects, many=True)

    class Meta:
        model = Action
        exclude = ('order',)


@register_view
class ActionViewSet(viewsets.ModelViewSet):
    queryset = Action.objects.all()
    serializer_class = ActionSerializer
    filterset_fields = {
        'plan': ('exact',),
        'categories': ('exact',)
    }


class ActionTaskSerializer(serializers.HyperlinkedModelSerializer):
    included_serializers = {
        'action': ActionTask,
    }

    class Meta:
        model = ActionTask
        exclude = ('completed_by',)


@register_view
class ActionTaskViewSet(viewsets.ModelViewSet):
    queryset = ActionTask.objects.all()
    serializer_class = ActionTaskSerializer


class ScenarioSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Scenario
        fields = '__all__'


@register_view
class ScenarioViewSet(viewsets.ModelViewSet):
    queryset = Scenario.objects.all()
    serializer_class = ScenarioSerializer
