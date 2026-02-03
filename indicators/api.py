from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast, override

from django.db import transaction
from django.db.models import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from rest_framework import exceptions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

import django_filters as filters
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field

from kausal_common.api.bulk import BulkListSerializer
from kausal_common.api.utils import register_view_helper
from kausal_common.users import user_or_bust, user_or_none

from aplans.permissions import WatchObjectPermissions
from aplans.rest_api import get_plan_from_view

from actions.api import AuditLoggingBulkModelViewSet, plan_router
from actions.models import Plan
from people.models import Person

from .models import (
    ActionIndicator,
    DimensionCategory,
    Indicator,
    IndicatorContactPerson,
    IndicatorGoal,
    IndicatorLevel,
    IndicatorValue,
    Quantity,
    RelatedIndicator,
    Unit,
)

if TYPE_CHECKING:
    from django.db.models import Model
    from django.views.generic import View
    from rest_framework.request import Request

    from indicators.models.indicator import IndicatorQuerySet
    from users.models import User

all_views = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class QuantitySerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='name_i18n')

    class Meta:
        model = Quantity
        fields = ('id', 'name')


@register_view
class QuantityViewSet(viewsets.ModelViewSet):
    queryset = Quantity.objects.all()
    serializer_class = QuantitySerializer


class UnitSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source='name_i18n')

    class Meta:
        model = Unit
        fields = ('id', 'name', 'verbose_name')


@register_view
class UnitViewSet(viewsets.ModelViewSet):
    queryset = Unit.objects.all()
    serializer_class = UnitSerializer


class IndicatorLevelSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndicatorLevel
        fields = ('plan', 'level')


class RelatedCausalIndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = RelatedIndicator
        fields = ('causal_indicator', 'effect_type', 'confidence_level')


class RelatedEffectIndicatorSerializer(serializers.ModelSerializer):
    class Meta:
        model = RelatedIndicator
        fields = ('effect_indicator', 'effect_type', 'confidence_level')


class IndicatorFilter(filters.FilterSet):
    plans = filters.ModelMultipleChoiceFilter(
        field_name='plans__identifier', to_field_name='identifier',
        queryset=Plan.objects,
    )

    class Meta:
        model = Indicator
        fields = ('plans', 'identifier', 'organization', 'name')


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
            cat_ids = sample.get('categories', [])
            categories = tuple(sorted([x.id for x in cat_ids]))
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
        created_or_updated_objects = []

        indicator_values = indicator.values.all().prefetch_related('categories').select_for_update()
        with transaction.atomic():
            existing_values_by_date_and_categories = dict()
            for val in indicator_values:
                date = val.date.isoformat()
                categories = tuple(sorted(val.categories.values_list('pk', flat=True)))
                existing_values_by_date_and_categories[(date,) + categories] = val

            for data in validated_data:
                categories = data.pop('categories', [])
                date = data.get('date').isoformat()

                sorted_category_pks = tuple(sorted([c.pk for c in categories]))
                try:
                    existing_indicator_value = existing_values_by_date_and_categories.pop((date,) + sorted_category_pks)
                except KeyError:
                    obj = IndicatorValue.objects.create(indicator=indicator, **data)
                    if categories:
                        obj.categories.set(categories)
                        created_or_updated_objects.append(obj)
                    continue
                existing_indicator_value.value = data['value']
                existing_indicator_value.save()
                created_or_updated_objects.append(existing_indicator_value)

            # If there are values in the database not in the data, delete them
            for indicator_value in existing_values_by_date_and_categories.values():
                indicator_value.delete()
            indicator.latest_value = None
            indicator.handle_values_update()

            for plan in indicator.plans.all():
                plan.invalidate_cache()

        return created_or_updated_objects


class IndicatorGoalListSerializer(serializers.ListSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        seen_dates = set()
        for sample in data:
            date = sample['date']
            if date in seen_dates:
                raise ValidationError("Duplicate date values")
            if 'value' not in sample or sample['value'] is None:
                raise ValidationError("Value is required")
            seen_dates.add(date)
        return data

    def create(self, validated_data):
        indicator = self.context['indicator']
        created_objs = []

        with transaction.atomic():
            indicator.goals.all().delete()

            for data in validated_data:
                obj = IndicatorGoal(indicator=indicator, **data)
                obj.save()
                created_objs.append(obj)

            indicator.handle_goals_update()

        return created_objs


class IndicatorDataPointMixin:
    def validate_date(self, date):
        indicator = self.context['indicator']
        if indicator.time_resolution == 'year':
            if date.day != 31 or date.month != 12:
                raise ValidationError(
                    "Indicator has a yearly resolution, so '%s' must be '%d-12-31" % (date, date.year),
                )
        elif indicator.time_resolution == 'month':
            if date.day != 1:
                raise ValidationError(
                    "Indicator has a monthly resolution, so '%s' must be '%d-%02d-01" % (date, date.year, date.month),
                )
        return date


class IndicatorValueSerializer(serializers.ModelSerializer, IndicatorDataPointMixin):
    # Explicit declaration required because ManyToManyField with explicit through model
    # is not automatically handled by DRF's ModelSerializer
    categories = serializers.PrimaryKeyRelatedField(
        queryset=DimensionCategory.objects.all(),
        many=True,
        required=False,
    )

    def validate_categories(self, cats):
        indicator = self.context['indicator']

        dims = [x.dimension for x in indicator.dimensions.all()]
        cat_by_id = {}
        for dim in dims:
            for cat in dim.categories.all():
                cat_by_id[cat.id] = cat

        found_dims = set()
        for cat in cats:
            c = cat_by_id.get(cat.id)
            if c is None:
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


@extend_schema_field(dict(
    type='object',
    title=_('Contact persons'),
))
class IndicatorContactPersonSerializer(serializers.ListSerializer):
    child = serializers.PrimaryKeyRelatedField(queryset=Person.objects.all())
    class Meta:
        model = IndicatorContactPerson
        fields = ('id', 'person', 'order')
        read_only_fields = ('id', 'order')

    def update(self, instance: Indicator, validated_data):
        assert isinstance(instance, Indicator)
        assert instance.pk is not None
        instance.set_contact_persons(validated_data)

    def to_representation(self, value):
        key = self.get_type_label()
        fk_id_label = f'{key}_id'
        return [{
            key: getattr(v, fk_id_label),
        } for v in value.all()]

    def to_internal_value(self, data):
        if isinstance(data, dict) and 'contact_persons' in data:
            data = data['contact_persons']
        return [{'person': item['person']} for item in data]

    def get_type_label(self):
        return 'person'

    def _cache_available_persons(self, plan) -> set[int]:
        cache = self.context.get('_cache', {})
        available_persons = cache.get('available_person_ids')
        if available_persons is None:
            available_persons = set(Person.objects.get_queryset().available_for_plan(
                plan, include_contact_persons=True).values_list('id', flat=True))
            cache['available_person_ids'] = available_persons
        return available_persons

    def get_available_instances(self, plan) -> set[int]:
        available_persons = self._cache_available_persons(plan)
        return available_persons

    def _cache_persons(self, pk) -> dict:
        cache = self.context.get('_cache', {})
        persons = cache.get('persons_by_id')
        if persons is None:
            persons = {p.pk: p for p in Person.objects.all()}
            cache['persons_by_id'] = persons
        return persons

    def get_instance_by_id(self, pk):
        persons = self._cache_persons(pk)
        return persons[pk]

    def get_multiple_error(self):
        return _("Person occurs multiple times as contact person")


def _validate_cat(ct_id, cat_val, ct_by_identifier) -> list:
    if ct_id not in ct_by_identifier:
            raise ValidationError('category type %s not found' % ct_id)
    ct = ct_by_identifier[ct_id]
    if not ct.usable_for_indicators or not ct.editable_for_indicators:
        raise ValidationError('category type %s not editable' % ct_id)
    cats = []
    if ct.select_widget == ct.SelectWidget.SINGLE:
        if cat_val is None:
            cat_ids = []
        else:
            if not isinstance(cat_val, int):
                raise ValidationError('invalid cat id: %s' % cat_val)
            cat_ids = [cat_val]
    else:
        if not isinstance(cat_val, list):
            raise ValidationError('expecting a list for %s' % ct_id)
        cat_ids = cat_val

    for cat_id in cat_ids:
        if not isinstance(cat_id, int):
            raise ValidationError('invalid cat id: %s' % cat_id)
        cat = ct.categories.filter(id=cat_id).first()
        if cat is None:
            raise ValidationError(
                'category %d not found in %s' % (cat_id, ct_id),
            )
        cats.append(cat)
    return cats


@extend_schema_field(dict(
    type='object',
    additionalProperties=dict(
        type='array',
        title='categories',
        items=dict(type='integer'),
    ),
))
class IndicatorCategoriesSerializer(serializers.Serializer):
    parent: IndicatorSerializer

    def to_representation(self, instance):
        request = self.context.get('request')
        user = None
        plan = None
        if request is not None and request.user and request.user.is_authenticated:
            user = request.user
            plan = user.get_active_admin_plan()
        else:
            return {}
        out = {}
        cats = instance.all()

        category_types = self._cache_cat_types(plan)

        for ct in category_types:
            if not ct.usable_for_indicators:
                continue
            ct_cats = [cat.id for cat in cats if cat.type_id == ct.pk]
            if ct.select_widget == ct.SelectWidget.SINGLE:
                val = ct_cats[0] if len(ct_cats) else None
            else:
                val = ct_cats
            out[ct.identifier] = val
        return out

    def to_internal_value(self, data):
        if not data:
            return {}
        request = self.context.get('request')
        user = None
        plan = None
        if request is not None and request.user and request.user.is_authenticated:
            user = request.user
            plan = user.get_active_admin_plan()
        else:
            return {}
        out = {}
        if not isinstance(data, dict):
            raise ValidationError('expecting a dict')

        category_types = self._cache_cat_types(plan)

        ct_by_identifier = {ct.identifier: ct for ct in category_types}
        for ct_id, cat_val in data.items():
            cats = _validate_cat(ct_id, cat_val, ct_by_identifier)
            out[ct_id] = cats
        return out

    def update(self, instance: Indicator, validated_data):
        assert isinstance(instance, Indicator)
        assert instance.pk is not None
        request = self.context.get('request')
        user = None
        plan = None
        if request is not None and request.user and request.user.is_authenticated:
            user = request.user
            plan = user.get_active_admin_plan()
        for ct_id, cats in validated_data.items():
            instance.set_categories(ct_id, cats, plan)

    def _cache_cat_types(self, plan) -> list:
        cache = self.context.get('_cache', {})
        category_types = cache.get('category_types')
        if category_types is None:
            category_types = list(plan.category_types.all().prefetch_related('categories'))
            cache['category_types'] = category_types
        return category_types


class IndicatorSerializerMixin:
    context: dict[str, Any]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.initialize_cache_context()

    def initialize_cache_context(self) -> None:
        request = self.context['request']
        if request is None:
            return
        user = user_or_none(request.user)
        if user is None:
            return
        plan = user.get_active_admin_plan(required=False)
        if plan is None:
            return

        cache: dict[str, Any] = {}

        # Ensure fields is a dictionary
        fields = cast(dict[str, serializers.Field], self.fields) # type: ignore[attr-defined]


        for field_name in ['categories', 'contact_persons']:
            if field_name in fields:
                fields[field_name].context['_cache'] = cache


class IndicatorSerializer(IndicatorSerializerMixin, serializers.ModelSerializer[Indicator]):
    _modifiable_indicators_cache: IndicatorQuerySet

    uuid = serializers.UUIDField(required=False)
    latest_value = IndicatorValueSerializer(read_only=True, required=False, label=_('Latest value'))
    contact_persons = IndicatorContactPersonSerializer(required=False, label=_('Contact persons'))
    categories = IndicatorCategoriesSerializer(required=False)
    # The level is in singular because an indicator is always manipulated in the
    # context of a single plan. The other levels of the indicator should be left
    # intact.
    level = serializers.ChoiceField(choices=Indicator.LEVELS, required=False, allow_null=True, label=_('Level'))

    class Meta:
        model = Indicator
        list_serializer_class = BulkListSerializer
        fields = (
            'id', 'uuid', 'name', 'quantity', 'unit', 'time_resolution', 'organization', 'updated_values_due_at',
            'latest_value', 'reference', 'internal_notes', 'visibility', 'contact_persons', 'categories',
            'description', 'level',
        )

    def to_representation(self, instance: Indicator) -> dict[str, Any]:
        representation = super().to_representation(instance)
        plan = self.context['plan']
        try:
            representation['level'] = instance.levels.get(plan=plan).level
        except ObjectDoesNotExist:
            representation['level'] = None
        return representation

    def create(self, validated_data: dict):
        contact_persons_data = validated_data.pop('contact_persons', None)
        categories_data = validated_data.pop('categories', None)
        _not_provided = object()
        level = validated_data.pop('level', _not_provided)
        instance = super().create(validated_data)

        fields = cast(dict[str, serializers.Field], self.fields)

        if categories_data is not None and hasattr(fields['categories'], 'update'):
            fields['categories'].update(instance, categories_data)
        if contact_persons_data is not None and hasattr(fields['contact_persons'], 'update'):
            fields['contact_persons'].update(instance, contact_persons_data)
        assert not instance.levels.exists()
        plan = self.context['plan']
        if level is _not_provided:
            level = 'strategic'
        if level is not None:
            assert level in [v for v, _ in Indicator.LEVELS]
            instance.levels.create(plan=plan, level=level)
        return instance

    def update(self, instance, validated_data):
        contact_persons_data = validated_data.pop('contact_persons', None)
        categories_data = validated_data.pop('categories', None)
        level = validated_data.pop('level', None)
        instance = super().update(instance, validated_data)

        fields = cast(dict[str, serializers.Field], self.fields)

        if categories_data is not None and hasattr(fields['categories'], 'update'):
            fields['categories'].update(instance, categories_data)
        if contact_persons_data is not None and hasattr(fields['contact_persons'], 'update'):
            fields['contact_persons'].update(instance, contact_persons_data)
        instance.save()

        plan = self.context['plan']
        if level is None:
            instance.levels.filter(plan=plan).delete()
        else:
            try:
                plan_level = instance.levels.get(plan=plan)
            except ObjectDoesNotExist:
                instance.levels.create(plan=plan, level=level)
            else:
                plan_level.level = level
                plan_level.save()

        return instance

    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        user = None
        plan = None
        if request is not None and request.user and request.user.is_authenticated:
            user = request.user
            plan = user.get_active_admin_plan()

        if user is None or not user.is_authenticated or (not user.is_superuser and not user.is_general_admin_for_plan(plan)):
            # Remove fields that are only for admins
            del fields['internal_notes']

        if user is not None:
            fields['modifiable_by_user'] = serializers.SerializerMethodField()

        return fields

    def get_modifiable_by_user(self, indicator: Indicator):
        if hasattr(self, '_modifiable_indicators_cache'):
            return indicator in self._modifiable_indicators_cache
        request: Request | None = self.context.get('request')
        if request is None:
            return False
        user = user_or_none(request.user)
        view = self.context.get('view')
        if user is None or view is None:
            return False
        self._modifiable_indicators_cache = view.get_queryset().modifiable_by(user)
        return indicator in self._modifiable_indicators_cache


class IndicatorGoalSerializer(serializers.ModelSerializer, IndicatorDataPointMixin):
    def to_internal_value(self, data):
        data['indicator_id'] = self.context['indicator'].pk
        return data

    class Meta:
        model = IndicatorGoal
        list_serializer_class = IndicatorGoalListSerializer
        fields = ['date', 'value']


class IndicatorEditValuesPermission(WatchObjectPermissions):
    model = IndicatorValue

    @override
    def check_permission(self, perm: str, user: User, view: View, obj: Model | None = None) -> bool:
        if perm in (f'indicators.{op}_indicatorvalue' for op in ('change', 'add', 'delete')):
            indicator_pk = view.kwargs.get('pk')
            try:
                indicator = Indicator.objects.get(id=indicator_pk)
            except Indicator.DoesNotExist as e:
                raise exceptions.NotFound(detail='Indicator not found') from e
            return user.can_modify_indicator(indicator=indicator)
        return False


class IndicatorPermission(WatchObjectPermissions):
    model = Indicator

    @override
    def check_permission(self, perm: str, user: User, view: View, obj: Model | None = None) -> bool:
        plan = get_plan_from_view(view)
        match perm:
            case 'indicators.change_indicator':
                assert obj is None or isinstance(obj, Indicator)
                return user.can_modify_indicator(indicator=obj)
            case 'indicators.add_indicator':
                assert obj is None
                return user.can_create_indicator(plan=plan)
            case 'indicators.delete_indicator':
                # For now we don't have object-specific delete permissions
                return user.can_delete_indicator(plan=plan)
        return False


@extend_schema(
    # Get rid of some warnings
    parameters=[
        OpenApiParameter(name='plan_id', type=OpenApiTypes.STR, location=OpenApiParameter.PATH),
    ],
)
class IndicatorViewSet(AuditLoggingBulkModelViewSet[Indicator]):
    serializer_class = IndicatorSerializer
    filterset_class = IndicatorFilter

    def get_plan(self) -> Plan | None:
        plan_pk = self.kwargs.get('plan_pk')
        if not plan_pk:
            return None
        return Plan.objects.get(pk=plan_pk)

    def get_queryset(self):
        plan = self.get_plan()
        if not plan:
            return Indicator.objects.none()
        return Indicator.objects.available_for_plan(plan).prefetch_related('contact_persons', 'categories')  # type: ignore[attr-defined]

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['plan'] = self.get_plan()
        return context

    def get_permissions(self):
        if self.action == 'update_values':
            return [IndicatorEditValuesPermission()]
        return [IndicatorPermission()]

    def check_object_permission(self, request, obj):
        super().check_object_permissions(request, obj)
        user = request.user
        if obj is not None:
            if not user.can_modify_indicator(obj):
                self.permission_denied(
                    request,
                    message='No permission to modify indicator',
                    code='no_indicator_permission',
                )
        elif not user.can_create_indicator(plan=None):
            self.permission_denied(
                request,
                message='No permission to modify indicator',
                code='no_indicator_permission',
            )

    @action(detail=True, methods=['get'])
    def values(self, request, plan_pk : int | None = None, pk=None):
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

    @goals.mapping.post
    def update_goals(self, request, plan_pk, pk):
        indicator = Indicator.objects.get(pk=pk)
        serializer = IndicatorGoalSerializer(data=request.data, many=True, context={'indicator': indicator})
        user = user_or_bust(request.user)
        if serializer.is_valid():
            serializer.create(serializer.validated_data)
            indicator.save_revision(
                user=user,
                log_action='indicator.update_goals',
            )
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return Response({})

    @values.mapping.post
    def update_values(self, request, plan_pk: int | None = None, pk: int | None = None):
        assert plan_pk is not None
        assert pk is not None
        indicator = Indicator.objects.prefetch_related(
            'dimensions', 'dimensions__dimension', 'dimensions__dimension__categories',
        ).get(pk=pk)
        serializer = IndicatorValueSerializer(data=request.data, many=True, context={'indicator': indicator})
        user = user_or_bust(self.request.user)
        if serializer.is_valid():
            serializer.create(serializer.validated_data)
            indicator.save_revision(
                user=user,
                log_action='indicator.update_values',
            )
        else:
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        return Response({})

    @action(detail=True, methods=['get'])
    def dimensions(self, request, pk=None):
        indicator = self.get_object()
        dimensions = [
            {
                'id': dim.dimension.id,
                'name': dim.dimension.name,
            }
            for dim in indicator.dimensions.all()
        ]
        return Response(dimensions)


plan_router.register('indicators', IndicatorViewSet, basename='indicator')


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
