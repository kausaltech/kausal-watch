from rest_framework import viewsets
from rest_framework_json_api import serializers
from rest_framework_json_api import views
from rest_framework_json_api.relations import ResourceRelatedField

from django_orghierarchy.models import Organization

from aplans.utils import register_view_helper
from aplans.model_images import ModelWithImageViewMixin, ModelWithImageSerializerMixin
from people.models import Person
from .models import (
    Plan, Action, ActionSchedule, Category, CategoryType, Scenario, ActionStatus,
    ActionTask, ActionDecisionLevel
)


all_views = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class PlanSerializer(ModelWithImageSerializerMixin, serializers.HyperlinkedModelSerializer):
    last_action_identifier = serializers.SerializerMethodField()

    included_serializers = {
        'action_schedules': 'actions.api.ActionScheduleSerializer',
    }

    def get_last_action_identifier(self, obj):
        return obj.actions.order_by('order').values_list('identifier', flat=True).last()

    class Meta:
        model = Plan
        fields = (
            'name', 'identifier', 'image_url', 'action_schedules',
            'last_action_identifier'
        )


@register_view
class PlanViewSet(ModelWithImageViewMixin, viewsets.ModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    filterset_fields = {
        'identifier': ('exact',),
    }


class ActionScheduleSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = ActionSchedule
        fields = '__all__'


@register_view
class ActionScheduleViewSet(viewsets.ModelViewSet):
    queryset = ActionSchedule.objects.all()
    serializer_class = ActionScheduleSerializer
    filterset_fields = {
        'plan': ('exact',),
        'plan__identifier': ('exact',),
    }


class ActionStatusSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = ActionStatus
        fields = '__all__'


@register_view
class ActionStatusViewSet(viewsets.ModelViewSet):
    queryset = ActionStatus.objects.all()
    serializer_class = ActionStatusSerializer
    filterset_fields = {
        'plan': ('exact',),
        'plan__identifier': ('exact',),
    }


class ActionDecisionLevelSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = ActionDecisionLevel
        fields = '__all__'


@register_view
class ActionDecisionLevelViewSet(viewsets.ModelViewSet):
    queryset = ActionDecisionLevel.objects.all()
    serializer_class = ActionDecisionLevelSerializer
    filterset_fields = {
        'plan': ('exact',),
        'plan__identifier': ('exact',),
    }


class CategoryTypeSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = CategoryType
        fields = '__all__'


@register_view
class CategoryTypeViewSet(viewsets.ModelViewSet):
    queryset = CategoryType.objects.all()
    serializer_class = CategoryTypeSerializer
    filterset_fields = {
        'plan': ('exact',),
        'plan__identifier': ('exact',),
    }


class CategorySerializer(serializers.HyperlinkedModelSerializer, ModelWithImageSerializerMixin):
    included_serializers = {
        'parent': 'actions.api.CategorySerializer',
    }

    class Meta:
        model = Category
        fields = '__all__'


@register_view
class CategoryViewSet(viewsets.ModelViewSet, ModelWithImageViewMixin):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    filterset_fields = {
        'type': ('exact', 'in'),
        'type__plan': ('exact',),
        'type__plan__identifier': ('exact',),
    }


class OrganizationSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Organization
        fields = ('id', 'name', 'abbreviation', 'parent')


@register_view
class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer


class PersonSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()

    def get_avatar_url(self, obj):
        return obj.get_avatar_url()

    class Meta:
        model = Person
        fields = ('first_name', 'last_name', 'avatar_url')


class ActionSerializer(serializers.HyperlinkedModelSerializer, ModelWithImageSerializerMixin):
    included_serializers = {
        'plan': PlanSerializer,
        'schedule': ActionScheduleSerializer,
        'status': ActionStatusSerializer,
        'categories': CategorySerializer,
        'responsible_parties': OrganizationSerializer,
        'tasks': 'actions.api.ActionTaskSerializer',
        'indicators': 'indicators.api.IndicatorSerializer',
        'decision_level': ActionDecisionLevelSerializer,
        'contact_persons': PersonSerializer,
    }
    tasks = ResourceRelatedField(queryset=ActionTask.objects, many=True)
    contact_persons = serializers.SerializerMethodField()

    def get_contact_persons(self, obj):
        return [
            dict(first_name=x.first_name, last_name=x.last_name, avatar_url=x.get_avatar_url())
            for x in obj.contact_persons.all()
        ]

    class Meta:
        model = Action
        exclude = ('order',)


@register_view
class ActionViewSet(views.ModelViewSet, ModelWithImageViewMixin):
    queryset = Action.objects.all()
    prefetch_for_includes = {
        '__all__': [
            'indicators', 'responsible_parties', 'schedule', 'categories', 'tasks',
            'contact_persons',
        ],
        'plan': ['plan'],
        'status': ['status'],
        'decision_level': ['decision_level'],
    }
    serializer_class = ActionSerializer
    filterset_fields = {
        'plan': ('exact',),
        'plan__identifier': ('exact',),
        'identifier': ('exact',),
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
    filterset_fields = {
        'action': ('exact',),
    }


class ScenarioSerializer(serializers.HyperlinkedModelSerializer):
    class Meta:
        model = Scenario
        fields = '__all__'


@register_view
class ScenarioViewSet(viewsets.ModelViewSet):
    queryset = Scenario.objects.all()
    serializer_class = ScenarioSerializer
    filterset_fields = {
        'plan': ('exact',),
        'plan__identifier': ('exact',),
    }
