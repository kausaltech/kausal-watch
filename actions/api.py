from django.utils.translation import gettext_lazy as _

from rest_framework import (
    viewsets, serializers, permissions, exceptions, relations
)
from rest_framework_nested import routers
from actions.models.action import ActionImplementationPhase
from aplans.types import AuthenticatedWatchRequest


from aplans.utils import register_view_helper, public_fields
from aplans.model_images import ModelWithImageViewMixin, ModelWithImageSerializerMixin
from orgs.models import Organization
from people.models import Person
from users.models import User
from .models import (
    Plan, Action, ActionImpact, ActionSchedule, Category, CategoryType, Scenario, ActionStatus,
    ActionTask, ActionDecisionLevel, ImpactGroup, ImpactGroupAction
)
from aplans.api_router import router
from aplans.permissions import AnonReadOnly

all_views = []
all_routers = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class ActionImpactSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionImpact
        fields = public_fields(ActionImpact)


class ActionScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionSchedule
        fields = public_fields(ActionSchedule)


class ActionStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionStatus
        fields = public_fields(ActionStatus)


class ActionImplementationPhaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActionImplementationPhase
        fields = public_fields(ActionImplementationPhase)


class PlanSerializer(ModelWithImageSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = public_fields(
            Plan,
            add_fields=['url'],
            remove_fields=[
                'static_pages', 'general_content', 'blog_posts', 'indicator_levels',
                'monitoring_quality_points', 'action_impacts',
            ]
        )
        filterset_fields = {
            'identifier': ('exact',),
        }


class PlanViewSet(ModelWithImageViewMixin, viewsets.ModelViewSet):
    queryset = Plan.objects.all()
    serializer_class = PlanSerializer
    filterset_fields = {
        'identifier': ('exact',),
    }


router.register('plan', PlanViewSet, basename='plan')
plan_router = routers.NestedSimpleRouter(router, 'plan', lookup='plan')
all_routers.append(plan_router)


class ActionScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = ActionScheduleSerializer

    def get_queryset(self):
        return ActionSchedule.objects.filter(plan=self.kwargs['plan_pk'])


plan_router.register(
    'action_schedules', ActionScheduleViewSet, basename='action_schedule',
)


class ActionImplementationPhaseViewSet(viewsets.ModelViewSet):
    serializer_class = ActionImplementationPhaseSerializer

    def get_queryset(self):
        return ActionImplementationPhase.objects.filter(plan=self.kwargs['plan_pk'])


plan_router.register(
    'action_implementation_phases', ActionImplementationPhaseViewSet, basename='action_implementation_phase',
)


class ActionPermission(permissions.DjangoObjectPermissions):
    def check_action_permission(self, user: User, perm: str, plan: Plan, action: Action = None):
        # Check for object permissions first
        if not user.has_perms(perm):
            return False
        if perm == 'actions.change_action':
            if not user.can_modify_action(plan=plan):
                return False
        elif perm == 'actions.add_action':
            if not user.can_create_action(plan=plan):
                return False
        elif perm == 'actions.delete_action':
            if not user.can_delete_action(plan=plan):
                return False
        else:
            return False
        return True

    def has_permission(self, request: AuthenticatedWatchRequest, view):
        plan_pk = view.kwargs['plan_pk']
        plan = Plan.objects.filter(id=plan_pk).first()
        if plan is None:
            raise exceptions.NotFound(detail='Plan not found')
        perms = self.get_required_permissions(request.method, Action)
        for perm in perms:
            if not self.check_action_permission(request.user, perm, plan):
                return False
        return True

    def has_object_permission(self, request, view, obj):
        perms = self.get_required_object_permissions(request.method, Action)
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        for perm in perms:
            if not self.check_action_permission(request.user, perm, obj.plan, obj):
                return False
        return True


class CategoriesSerializer(serializers.Serializer):
    def to_representation(self, instance):
        s = self.parent
        plan: Plan = s.plan
        out = {}
        cats = instance.all()

        for ct in plan.category_types.all():
            if not ct.usable_for_actions:
                continue
            ct_cats = [cat.id for cat in cats if cat.type_id == ct.id]
            if ct.select_widget == ct.SelectWidget.SINGLE:
                val = ct_cats[0] if len(ct_cats) else None
            else:
                val = ct_cats
            out[ct.identifier] = val
        return out

    def to_internal_value(self, data):
        if not data:
            return {}

        s = self.parent
        plan: Plan = s.plan
        out = {}
        if not isinstance(data, dict):
            raise exceptions.ValidationError('expecting a dict')
        ct_by_identifier = {ct.identifier: ct for ct in plan.category_types.all()}
        for ct_id, cat_val in data.items():
            if ct_id not in ct_by_identifier:
                raise exceptions.ValidationError('category type %s not found' % ct_id)
            ct = ct_by_identifier[ct_id]
            if not ct.usable_for_actions or not ct.editable_for_actions:
                raise exceptions.ValidationError('category type %s not editable' % ct_id)
            cats = []
            if ct.select_widget == ct.SelectWidget.SINGLE:
                if cat_val is None:
                    cat_ids = []
                else:
                    if not isinstance(cat_val, int):
                        raise exceptions.ValidationError('invalid cat id: %s' % cat_val)
                    cat_ids = [cat_val]
            else:
                if not isinstance(cat_val, list):
                    raise exceptions.ValidationError('expecting a list for %s' % ct_id)
                cat_ids = cat_val

            for cat_id in cat_ids:
                if not isinstance(cat_id, int):
                    raise exceptions.ValidationError('invalid cat id: %s' % cat_id)
                cat = ct.categories.filter(id=cat_id).first()
                if cat is None:
                    raise exceptions.ValidationError(
                        'category %d not found in %s' % (cat_id, ct_id)
                    )
                cats.append(cat)
            out[ct_id] = cats
        return out

    def update(self, instance: Action, validated_data):
        assert isinstance(instance, Action)
        assert instance.pk is not None
        for ct_id, cats in validated_data.items():
            instance.set_categories(ct_id, cats)


class ActionSerializer(serializers.ModelSerializer):
    plan: Plan
    categories = CategoriesSerializer(required=False)

    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan', None)
        if not self.plan:
            view = kwargs['context']['view']
            plan_pk = view.kwargs['plan_pk']
            self.plan = Plan.objects.filter(pk=plan_pk).prefetch_related('category_types').first()
            if self.plan is None:
                raise exceptions.NotFound('Plan not found')
        super().__init__(*args, **kwargs)

    def get_fields(self):
        fields = super().get_fields()
        request: AuthenticatedWatchRequest = self.context.get('request')
        user = None
        if request is not None and request.user and request.user.is_authenticated:
            user = request.user

        if user is None or (not user.is_superuser and not user.is_general_admin_for_plan(self.plan)):
            # Remove fields that are only for admins
            del fields['internal_notes']
            del fields['internal_admin_notes']

        return fields

    def build_field(self, field_name, info, model_class, nested_depth):
        field_class, field_kwargs = super().build_field(field_name, info, model_class, nested_depth)
        if field_name in ('status', 'implementation_phase', 'decision_level', 'schedule', 'merged_with'):
            field_kwargs['queryset'] = field_kwargs['queryset'].filter(plan=self.plan)
        elif field_name == 'primary_org':
            if self.plan.features.has_action_primary_orgs:
                field_kwargs['allow_null'] = False
                field_kwargs['queryset'] = self.plan.get_related_organizations()
            else:
                field_kwargs['queryset'] = Organization.objects.none()

        return field_class, field_kwargs

    def validate_identifier(self, value):
        if not self.plan.features.has_action_identifiers:
            return value

        if not value:
            raise serializers.ValidationError(_('Identifier must be set'))

        qs = self.plan.actions.filter(identifier=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(_('Identifier already exists'))

        return value

    def create(self, validated_data: dict):
        validated_data['plan'] = self.plan
        categories = validated_data.pop('categories', None)
        instance = super().create(validated_data)
        if categories is not None:
            self.fields['categories'].update(instance, categories)
        return instance

    def update(self, instance, validated_data):
        categories = validated_data.pop('categories', None)
        validated_data.pop('plan', None)
        instance = super().update(instance, validated_data)
        if categories is not None:
            self.fields['categories'].update(instance, categories)
        return instance

    class Meta:
        model = Action
        fields = public_fields(
            Action,
            add_fields=['internal_notes', 'internal_admin_notes'],
            remove_fields=[
                'responsible_parties', 'contact_persons', 'impact',
                'status_updates', 'monitoring_quality_points', 'image',
                'tasks', 'links', 'related_indicators', 'indicators',
                'impact_groups', 'merged_actions',
            ]
        )
        read_only_fields = ['plan']


class ActionViewSet(viewsets.ModelViewSet):
    serializer_class = ActionSerializer

    def get_permissions(self):
        if self.action == 'list':
            permission_classes = [AnonReadOnly]
        else:
            permission_classes = [ActionPermission]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        return Action.objects.filter(plan=self.kwargs['plan_pk'])\
            .prefetch_related('schedule', 'categories')


plan_router.register(
    'actions', ActionViewSet, basename='action',
)


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


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ('id', 'name', 'abbreviation',)


@register_view
class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    filterset_fields = {
        'name': ('exact', 'in'),
    }


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


class ImpactGroupActionSerializer(serializers.HyperlinkedModelSerializer):
    impact = ActionImpactSerializer()

    class Meta:
        model = ImpactGroupAction
        fields = public_fields(ImpactGroupAction)


@register_view
class ImpactGroupActionViewSet(viewsets.ModelViewSet):
    queryset = ImpactGroupAction.objects.all()
    serializer_class = ImpactGroupActionSerializer
