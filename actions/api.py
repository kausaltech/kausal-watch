from rest_framework import viewsets, serializers, permissions

from django_orghierarchy.models import Organization

from aplans.utils import register_view_helper, public_fields
from aplans.model_images import ModelWithImageViewMixin, ModelWithImageSerializerMixin
from people.models import Person
from .models import (
    Plan, Action, ActionSchedule, Category, CategoryType, Scenario, ActionStatus,
    ActionTask, ActionDecisionLevel, ImpactGroup, ImpactGroupAction
)


all_views = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class ActionImpactSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionDecisionLevel
        fields = '__all__'


class PlanSerializer(ModelWithImageSerializerMixin, serializers.HyperlinkedModelSerializer):
    action_impacts = ActionImpactSerializer(many=True)

    class Meta:
        model = Plan
        fields = public_fields(
            Plan,
            add_fields=['url'],
            remove_fields=[
                'static_pages', 'general_content', 'blog_posts', 'indicator_levels',
                'monitoring_quality_points'
            ]
        )
        filterset_fields = {
            'identifier': ('exact',),
        }


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


class PersonSerializer(serializers.HyperlinkedModelSerializer, ModelWithImageSerializerMixin):
    avatar_url = serializers.SerializerMethodField()

    def get_avatar_url(self, obj):
        return obj.get_avatar_url(self.context['request'])

    class Meta:
        model = Person
        fields = ('first_name', 'last_name', 'avatar_url')


@register_view
class PersonViewSet(ModelWithImageViewMixin, viewsets.ModelViewSet):
    queryset = Person.objects.all()
    serializer_class = PersonSerializer


class ActionSerializer(serializers.HyperlinkedModelSerializer, ModelWithImageSerializerMixin):
    class Meta:
        model = Action
        fields = public_fields(Action, remove_fields=[
            'responsible_parties', 'contact_persons', 'impact', 'status_updates', 'monitoring_quality_points'
        ])


@register_view
class ActionViewSet(viewsets.ModelViewSet, ModelWithImageViewMixin):
    queryset = Action.objects.all()
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


class ImpactGroupSerializer(serializers.HyperlinkedModelSerializer):
    name = serializers.CharField()  # translated field

    class Meta:
        model = ImpactGroup
        fields = public_fields(ImpactGroup, remove_fields=['actions'])


@register_view
class ImpactGroupViewSet(viewsets.ModelViewSet):
    queryset = ImpactGroup.objects.all()
    permission_classes = (permissions.DjangoModelPermissionsOrAnonReadOnly,)
    serializer_class = ImpactGroupSerializer
    filterset_fields = {
        'plan': ('exact',),
        'plan__identifier': ('exact',),
    }
