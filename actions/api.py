from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Protocol, cast
from uuid import UUID

import rest_framework.fields
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from modeltrans.translator import get_i18n_field
from modeltrans.utils import build_localized_fieldname, get_available_languages
from rest_framework import exceptions, permissions, serializers, viewsets
from rest_framework.relations import RelatedField
from rest_framework.routers import SimpleRouter

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field
from rest_framework_nested import routers

from kausal_common.api.bulk import BulkListSerializer, BulkModelViewSet, BulkSerializerValidationInstanceMixin
from kausal_common.api.exceptions import HandleProtectedErrorMixin
from kausal_common.api.tree import PrevSiblingField, TreebeardModelSerializerMixin
from kausal_common.api.utils import RegisteredAPIView, register_view_helper
from kausal_common.model_images import (
    ModelWithImageSerializerMixin,
    ModelWithImageViewMixin,
)
from kausal_common.people.api import PersonSerializer as BasePersonSerializer
from kausal_common.users import user_or_none

from aplans.api_router import router
from aplans.permissions import AnonReadOnly
from aplans.rest_api import PlanRelatedModelSerializer
from aplans.utils import generate_identifier, public_fields

from actions.models.action import ActionContactPerson, ActionImplementationPhase, ActionQuerySet
from actions.models.attributes import Attribute, AttributeType, ModelWithAttributes
from orgs.models import Organization
from pages.apps import post_reorder_categories
from people.models import Person, PersonQuerySet

from .deferred_ops import DeferredDatabaseOperationsMixin
from .models import (
    Action,
    ActionDecisionLevel,
    ActionImpact,
    ActionResponsibleParty,
    ActionSchedule,
    ActionStatus,
    ActionTask,
    Category,
    CategoryType,
    ImpactGroup,
    ImpactGroupAction,
    Plan,
    Scenario,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.models import Model, QuerySet
    from rest_framework.request import Request
    from rest_framework.routers import BaseRouter

    from aplans.types import WatchAdminRequest, WatchAPIRequest

    from actions.models.plan import PlanQuerySet
    from users.models import User

all_views: list[RegisteredAPIView] = []
all_routers: list[BaseRouter] = []


def register_view(klass: type[viewsets.GenericViewSet[Any]], *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class BulkRouter(SimpleRouter):
    routes = copy.deepcopy(SimpleRouter.routes)
    routes[0].mapping.update(  # type: ignore[union-attr]
        {
            'put': 'bulk_update',
            'patch': 'partial_bulk_update',
        }
    )


class NestedBulkRouter(routers.NestedDefaultRouter, BulkRouter):
    pass


class ActionImpactSerializer(serializers.ModelSerializer[ActionImpact]):
    class Meta:
        model = ActionImpact
        fields = public_fields(ActionImpact)


class ActionScheduleSerializer(serializers.ModelSerializer[ActionSchedule]):
    class Meta:
        model = ActionSchedule
        fields = public_fields(ActionSchedule)


class ActionStatusSerializer(serializers.ModelSerializer[ActionStatus]):
    class Meta:
        model = ActionStatus
        fields = public_fields(ActionStatus)


class ActionImplementationPhaseSerializer(serializers.ModelSerializer[ActionImplementationPhase]):
    class Meta:
        model = ActionImplementationPhase
        fields = public_fields(ActionImplementationPhase)


class PlanSerializer(ModelWithImageSerializerMixin, serializers.ModelSerializer[Plan]):
    class Meta:
        model = Plan
        fields = public_fields(
            Plan,
            add_fields=['url'],
            remove_fields=[
                'static_pages',
                'general_content',
                'blog_posts',
                'indicator_levels',
                'monitoring_quality_points',
                'action_impacts',
                'superseded_plans',
            ],
        )
        filterset_fields = {
            'identifier': ('exact',),
        }


class PlanViewSet(ModelWithImageViewMixin, viewsets.ModelViewSet[Plan]):
    queryset = Plan.objects.get_queryset()
    serializer_class = PlanSerializer
    filterset_fields = {
        'identifier': ('exact',),
    }

    @classmethod
    def get_available_plans(
        cls,
        queryset: PlanQuerySet | None = None,
        request: Request | None = None,
    ) -> PlanQuerySet:
        user = user_or_none(request.user) if request else None

        if queryset is None:
            queryset = Plan.objects.get_queryset()
            assert queryset is not None

        if user is not None:
            return queryset.live() | queryset.filter(id__in=user.get_adminable_plans())
        return queryset.live()

    @classmethod
    def get_default_plan(
        cls,
        queryset: PlanQuerySet | None = None,
        request: Request | None = None,
    ) -> Plan:
        plans = cls.get_available_plans(queryset=queryset, request=request)
        plan = None
        if request is not None and hasattr(request, 'get_active_admin_plan'):
            admin_plan = request.get_active_admin_plan()
            plan = plans.filter(id=admin_plan.id).first()

        if plan is None:
            plan = plans.first()
        assert plan is not None
        return plan

    def get_queryset(self) -> PlanQuerySet:
        qs = cast('PlanQuerySet', super().get_queryset())
        return self.get_available_plans(qs, self.request)


router.register('plan', PlanViewSet, basename='plan')
plan_router = NestedBulkRouter(router, 'plan', lookup='plan')
all_routers.append(plan_router)


class ActionScheduleViewSet(viewsets.ModelViewSet[ActionSchedule]):
    serializer_class = ActionScheduleSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Called during schema generation
            return ActionSchedule.objects.none()
        return ActionSchedule.objects.filter(plan=self.kwargs['plan_pk'])


plan_router.register(
    'action_schedules',
    ActionScheduleViewSet,
    basename='action_schedule',
)


class ActionImplementationPhaseViewSet(viewsets.ModelViewSet[ActionImplementationPhase]):
    serializer_class = ActionImplementationPhaseSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Called during schema generation
            return ActionImplementationPhase.objects.none()
        return ActionImplementationPhase.objects.filter(plan=self.kwargs['plan_pk'])


plan_router.register(
    'action_implementation_phases',
    ActionImplementationPhaseViewSet,
    basename='action_implementation_phase',
)


class ActionPermission(permissions.DjangoObjectPermissions):
    # TODO: Refactor duplicated code with ActionPermission, CategoryPermission, OrganizationPermission and PersonPermission
    def check_permission(self, user: User, perm: str, plan: Plan, action: Action | None = None):
        # Check for object permissions first
        if not user.has_perms([perm]):
            return False
        if perm == 'actions.change_action':
            if not user.can_modify_action(action=action, plan=plan):
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

    def has_permission(self, request: Request, view):
        plan_pk = view.kwargs.get('plan_pk')
        if plan_pk:
            plan = Plan.objects.filter(id=plan_pk).first()
            if plan is None:
                raise exceptions.NotFound(detail='Plan not found')
        else:
            plan = Plan.objects.get_queryset().live().first()
            assert plan is not None
        if request.method is None:
            return False
        perms = self.get_required_permissions(request.method, Action)
        user = user_or_none(request.user)
        if user is None:
            return False
        return all(self.check_permission(user, perm, plan) for perm in perms)

    def has_object_permission(self, request, view, obj):
        if request.method is None:
            return False
        perms = self.get_required_object_permissions(request.method, Action)
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        user = user_or_none(request.user)
        if user is None:
            return False
        return all(self.check_permission(user, perm, obj.plan, obj) for perm in perms)


@extend_schema_field(
    dict(
        type='object',
        additionalProperties=dict(
            type='array',
            title='categories',
            items=dict(type='integer'),
        ),
    )
)
class ActionCategoriesSerializer(serializers.Serializer):
    parent: ActionSerializer

    def to_representation(self, instance):
        s = self.parent
        plan: Plan = s.plan
        out = {}
        cats = instance.all()

        for ct in plan.category_types.all():
            if not ct.usable_for_actions:
                continue
            ct_cats = [cat.id for cat in cats if cat.type_id == ct.pk]
            if ct.select_widget == ct.SelectWidget.SINGLE:
                val = ct_cats[0] if len(ct_cats) > 0 else None
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
                        'category %d not found in %s' % (cat_id, ct_id),
                    )
                cats.append(cat)
            out[ct_id] = cats
        return out

    def update(self, instance: Action, validated_data):
        assert isinstance(instance, Action)
        assert instance.pk is not None
        for ct_id, cats in validated_data.items():
            instance.set_categories(ct_id, cats)


class ActionResponsibleWithRoleSerializer(serializers.Serializer):
    parent: ActionSerializer

    def get_type_label(self):
        raise NotImplementedError()

    def get_available_instances(self, plan) -> QuerySet:
        raise NotImplementedError()

    def get_allowed_roles(self):
        raise NotImplementedError()

    def get_queryset(self):
        raise NotImplementedError()

    def set_instance_values(self, instance, data):
        raise NotImplementedError()

    def get_multiple_error(self):
        raise NotImplementedError()

    def to_representation(self, value):
        key = self.get_type_label()
        fk_id_label = f'{key}_id'
        return [
            {
                key: getattr(v, fk_id_label),
                'role': v.role,
            }
            for v in value.all()
        ]

    def to_internal_value(self, data):
        s = self.parent
        plan: Plan = s.plan
        if not isinstance(data, list):
            raise exceptions.ValidationError('expecting a list')
        available_instances = self.get_available_instances(plan)
        seen_instances = set()
        key = self.get_type_label()

        for val in data:
            instance_id = val.get(key, None)
            role = val.get('role', None)
            if not (isinstance(val, dict) and isinstance(instance_id, int) and (role is None or isinstance(role, str))):
                raise exceptions.ValidationError(
                    'expecting a list of dicts mapping "organization" to int and "role" to str or None',
                )
            if val[key] not in available_instances:
                raise exceptions.ValidationError('%d not available for plan' % val[key])
            if val['role'] not in self.get_allowed_roles():
                raise exceptions.ValidationError(f'{val["role"]} is not a valid role')
            if instance_id in seen_instances:
                raise exceptions.ValidationError(self.get_multiple_error())
            seen_instances.add(instance_id)
            val[key] = self.get_instance_by_id(instance_id)
        return data

    def update(self, instance: Action, validated_data):
        assert isinstance(instance, Action)
        assert instance.pk is not None
        self.set_instance_values(instance, validated_data)


@extend_schema_field(
    dict(
        type='object',
        title=_('Responsible parties'),
    )
)
class ActionResponsiblePartySerializer(ActionResponsibleWithRoleSerializer):
    def get_type_label(self):
        return 'organization'

    def get_available_instances(self, plan) -> set[int]:
        cache = self.context.get('_cache')
        if cache is None or 'available_organization_ids' not in cache:
            return Organization.objects.available_for_plan(plan)
        return cache['available_organization_ids']

    def get_allowed_roles(self):
        return ActionResponsibleParty.Role.values

    def get_instance_by_id(self, pk):
        cache = self.context.get('_cache')
        if cache is None or 'organizations_by_id' not in cache:
            return Organization.objects.get(id=pk)
        return cache['organizations_by_id'][pk]

    def set_instance_values(self, instance, data):
        instance.set_responsible_parties(data)

    def get_multiple_error(self):
        return _('Organization occurs multiple times as responsible party')


@extend_schema_field(
    dict(
        type='object',
        title=_('Contact persons'),
    )
)
class ActionContactPersonSerializer(ActionResponsibleWithRoleSerializer):
    def get_type_label(self):
        return 'person'

    def get_available_instances(self, plan) -> set[int]:
        cache = self.context.get('_cache')
        if cache is None or 'available_person_ids' not in cache:
            return Person.objects.get_queryset().available_for_plan(plan, include_contact_persons=True)
        return cache['available_person_ids']

    def get_allowed_roles(self):
        return ActionContactPerson.Role.values

    def get_instance_by_id(self, pk):
        cache = self.context.get('_cache')
        if cache is None or 'persons_by_id' not in cache:
            return Person.objects.get(id=pk)
        return cache['persons_by_id'][pk]

    def set_instance_values(self, instance, data):
        instance.set_contact_persons(data)

    def get_multiple_error(self):
        return _('Person occurs multiple times as contact person')


class AttributesSerializerMixin:
    context: dict[str, Any]
    attribute_formats: tuple[AttributeType.AttributeFormat, ...]

    def is_attribute_visible(self, attribute: Attribute) -> bool:
        request: WatchAPIRequest | None = self.context.get('request')
        if request is None or not hasattr(request, 'get_active_admin_plan'):
            return False
        plan = request.get_active_admin_plan()
        attribute_holder = attribute.content_object
        return attribute.type.is_instance_visible_for(request.user, plan, attribute_holder)

    # In the serializer, set `attribute_formats` to a tuple of values from `AttributeType.AttributeFormat`
    # (usually just one element)
    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request is not None and request.user and request.user.is_authenticated:
            user = request.user
            plan = user.get_active_admin_plan()
            attribute_types = plan.action_attribute_types.filter(format__in=self.attribute_formats)
            for attribute_type in attribute_types:
                if not attribute_type.is_instance_visible_for(user, plan, None):
                    continue
                if attribute_type.instance_editability_is_action_specific:
                    # Editability is specific to an action and we don't have one here
                    instances_editable = True
                else:
                    # Editability is not action-specific, so it's safe to call this
                    instances_editable = attribute_type.is_instance_editable_by(user, plan, None)
                # FIXME: Why the hell is this a FloatField?
                fields[attribute_type.identifier] = rest_framework.fields.FloatField(
                    label=attribute_type.name,
                    read_only=not instances_editable,
                )
        return fields

    def get_cached_values(self, instance_pk: int | None = None):
        if '_cache' not in self.context:
            return None
        if '_current_instance' not in self.context and instance_pk is None:
            return None
        # I was unable to access the individual serializable instance through serializer or its parents when serializing with a
        # listserializer. Hence, the need to store the instance in the context
        if instance_pk is None:
            instance_pk = self.context['_current_instance'].pk
        attributes = {}
        for format in self.attribute_formats:
            for action_pk, attribute_vals in self.context['_cache']['attribute_values'].get(format, {}).items():
                attributes.setdefault(action_pk, []).extend(attribute_vals)
        return attributes.get(instance_pk, [])

    def get_cached_attribute_type(self, attribute_type_identifier: str):
        if '_cache' not in self.context:
            return None
        attribute_type = self.context['_cache']['attribute_types'][attribute_type_identifier]
        return attribute_type

    def set_instance_attribute(self, instance, attribute_type, existing_attribute, item):
        return instance.set_attribute(
            attribute_type,
            existing_attribute,
            self.to_value_parameter(item),
            self.to_attribute_value_input(item),
        )

    def update(self, instance: Model, validated_data):
        assert instance.pk is not None
        cached_values = self.get_cached_values(instance_pk=instance.pk)
        attribute_operations = []
        for attribute_type_identifier, item in validated_data.items():
            attribute_type = self.get_cached_attribute_type(attribute_type_identifier)
            if cached_values is None:
                # We reach here when creating new host instances with new attributes
                existing_attributes = []
            else:
                existing_attributes = [cv for cv in cached_values if cv.type == attribute_type.instance]
            if len(existing_attributes) == 0:
                existing_attribute = None
            else:
                assert len(existing_attributes) == 1
                existing_attribute = existing_attributes[0]
            assert len(existing_attributes) < 2
            attribute_operations.append(
                self.set_instance_attribute(instance, attribute_type, existing_attribute, item),
            )
        return attribute_operations

    def to_attribute_value_input(self, item: Any) -> Any:
        """
        Format the incoming REST API data to conform
        to the format expected by each actions.attributes.AttributeValue
        subclass as the value parameter of the from_serialized_value method
        """
        return self.to_value_parameter(item)

    def to_value_parameter(self, item: Any) -> dict[str, Any]:
        """
        Format the incoming REST API data to conform
        to the format expected by an existing Attribute model
        instance, setting the instance attributes with

            setattr(instance, key_in_dict, value_parameter_dict[key_in_dict])

        This means the dict keys must be django model field names
        for that attribute type's attribute model instances
        and the corresponding dict values must be compatible
        values for that field.
        """
        raise NotImplementedError


class ChoiceAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_formats = (AttributeType.AttributeFormat.ORDERED_CHOICE, AttributeType.AttributeFormat.UNORDERED_CHOICE)

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {v.type.identifier: v.choice_id for v in values if self.is_attribute_visible(v)}

    def to_internal_value(self, data):
        return data

    def to_value_parameter(self, item):
        return {'choice_id': item}

    def to_attribute_value_input(self, item):
        return item


class ChoiceWithTextAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_formats = (AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT,)

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {
            v.type.identifier: {'choice': v.choice_id, 'text': v.text} for v in values if self.is_attribute_visible(v)
        }

    def to_internal_value(self, data):
        return data

    def to_value_parameter(self, item):
        return {
            'choice_id': item.get('choice'),
            'text': item.get('text'),
        }

    def to_attribute_value_input(self, item):
        return {
            'choice': item.get('choice'),
            'text': {'text': item.get('text')},
        }


class NumericValueAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_formats = (AttributeType.AttributeFormat.NUMERIC,)

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {v.type.identifier: v.value for v in values if self.is_attribute_visible(v)}

    def to_internal_value(self, data):
        return data

    def to_value_parameter(self, item):
        return {
            'value': item,
        }

    def to_attribute_value_input(self, item):
        return float(item)


class TextAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_formats = (AttributeType.AttributeFormat.TEXT,)

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {v.type.identifier: v.text for v in values if self.is_attribute_visible(v)}

    def to_internal_value(self, data):
        return data

    def to_value_parameter(self, item):
        return {
            'text': item,
        }


class RichTextAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_formats = (AttributeType.AttributeFormat.RICH_TEXT,)

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {v.type.identifier: v.text for v in values if self.is_attribute_visible(v)}

    def to_internal_value(self, data):
        return data

    def to_value_parameter(self, item):
        return {
            'text': item,
        }


class CategoryChoiceAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_formats = (AttributeType.AttributeFormat.CATEGORY_CHOICE,)

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {
            v.type.identifier: [cat.id for cat in v.categories.all()] for v in values if self.is_attribute_visible(v)
        }

    def to_internal_value(self, data):
        return data

    def set_instance_attribute(self, instance, attribute_type, existing_attribute, item):
        return instance.set_category_choice_attribute(
            attribute_type,
            existing_attribute,
            item,
        )


# Regarding the metaclass: https://stackoverflow.com/a/58304791/14595546
class ModelWithAttributesSerializerMixin(DeferredDatabaseOperationsMixin, metaclass=serializers.SerializerMetaclass):
    choice_attributes = ChoiceAttributesSerializer(required=False)
    choice_with_text_attributes = ChoiceWithTextAttributesSerializer(required=False)
    numeric_value_attributes = NumericValueAttributesSerializer(required=False)
    text_attributes = TextAttributesSerializer(required=False)
    rich_text_attributes = RichTextAttributesSerializer(required=False)
    category_choice_attributes = CategoryChoiceAttributesSerializer(required=False)

    _attribute_fields = [
        'choice_attributes',
        'choice_with_text_attributes',
        'numeric_value_attributes',
        'text_attributes',
        'rich_text_attributes',
        'category_choice_attributes',
    ]

    context: dict[str, Any]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initialize_cache_context()

    def initialize_cache_context(self):
        plan = self.context.get('plan')
        if plan is None:
            return
        Model = self.Meta.model
        attribute_types = Model.get_attribute_types_for_plan(plan)
        attribute_types_by_identifier = {at.instance.identifier: at for at in attribute_types}
        prepopulated_attributes: dict[str, dict] = {}
        content_type = ContentType.objects.get_for_model(Model)
        for at in attribute_types:
            prepopulated_attributes.setdefault(at.instance.format, {})
            for a in at.attributes.filter(content_type=content_type):
                prepopulated_attributes[at.instance.format].setdefault(a.object_id, []).append(a)

        available_organization_ids = set(Organization.objects.qs.available_for_plan(plan).values_list('id', flat=True))
        available_person_ids = set(
            Person.objects.qs.available_for_plan(plan, include_contact_persons=True).values_list('id', flat=True)
        )
        persons_by_id = {p.pk: p for p in Person.objects.all()}
        organizations_by_id = {o.pk: o for o in Organization.objects.all()}

        for field_name in self._attribute_fields:
            self.fields[field_name].context['_cache'] = {
                'attribute_values': prepopulated_attributes,
                'attribute_types': attribute_types_by_identifier,
                'available_organization_ids': available_organization_ids,
                'available_person_ids': available_person_ids,
                'persons_by_id': persons_by_id,
                'organizations_by_id': organizations_by_id,
            }

    def get_field_names(self, declared_fields, info):
        fields = super().get_field_names(declared_fields, info)
        fields += self._attribute_fields
        return fields

    def create(self, validated_data: dict):
        popped_fields = self._pop_attributes_from_validated_data(validated_data)
        instance = super().create(validated_data)
        self._update_attribute_fields(instance, popped_fields)
        return instance

    def update(self, instance, validated_data):
        popped_fields = self._pop_attributes_from_validated_data(validated_data)
        instance = super().update(instance, validated_data)
        self._update_attribute_fields(instance, popped_fields)
        return instance

    def _pop_attributes_from_validated_data(self, validated_data: dict):
        return {field: validated_data.pop(field, None) for field in self._attribute_fields}

    def _update_attribute_fields(self, instance: ModelWithAttributes, popped_fields):
        for field_name, data in popped_fields.items():
            if data is not None:
                ops = self.fields[field_name].update(instance, data)
                self.add_deferred_operations(ops)



class HasUUIDAndOrder(Protocol):
    uuid: UUID
    order: int


# Regarding the metaclass: https://stackoverflow.com/a/58304791/14595546
class NonTreebeardModelWithTreePositionSerializerMixin[M: HasUUIDAndOrder](
    DeferredDatabaseOperationsMixin, metaclass=serializers.SerializerMetaclass
):
    left_sibling = PrevSiblingField(allow_null=True, required=False)
    _cached_instances: dict[UUID, M]
    instance: M | None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance is not None:
            self.init_cached_instances(self.instance)

    def init_cached_instances(self, instance):
        # Use instance cache for bulk update
        def init_cache(force_refresh=False):
            self._cached_instances = {}
            # If we're using self as a list serializer, instance should be an iterable
            try:
                iter(instance)
            except TypeError:
                # Probably a single instance
                nodes = instance.get_siblings(force_refresh=force_refresh)
            else:
                nodes = instance
            for node in nodes:
                self._cache_descendants(node)
                # Model may or may not have parent field
                parent = getattr(instance, 'parent', None)
                if parent:
                    self._cached_instances[parent.uuid] = parent

        try:
            init_cache()
        except KeyError:
            # get_siblings is using a cache for performance reasons.  We need to clear the cache when adding new
            # nodes because the cache was initially initialized when the new nodes where not in the database.
            init_cache(force_refresh=True)

    def get_field_names(self, declared_fields, info):
        fields = super().get_field_names(declared_fields, info)
        # fields += self._tree_position_fields
        fields.append('left_sibling')
        return fields

    def create(self, validated_data: dict):
        left_sibling_uuid = validated_data.pop('left_sibling', None)
        instance = super().create(validated_data)
        self.init_cached_instances(instance)
        instance = self._cached_instances[instance.uuid]
        ops = self._update_tree_position(instance, left_sibling_uuid)
        self.add_deferred_operations(ops)
        return instance

    def update(self, instance, validated_data):
        # FIXME: Since left_sibling has allow_null=True, we should distinguish whether left_sibling is None because it
        # is not in validated_data or because validated_data['left_sibling'] is None. Sending a PUT request and omitting
        # left_sibling might inadvertently move the node.
        instance = self._cached_instances[instance.uuid]
        left_sibling_uuid = validated_data.pop('left_sibling', None)
        instance = super().update(instance, validated_data)
        ops = self._update_tree_position(instance, left_sibling_uuid)
        self.add_deferred_operations(ops)
        return instance

    # The following would make `order` unique only relative to parent, i.e., each first child gets order 0.
    # Unforutnately just ordering by the `order` field then gives unintended results. We'd like instances ordered by
    # DFS.
    # def _update_tree_position(self, instance, left_sibling):
    #     if left_sibling is None:
    #         new_order = 0
    #     else:
    #         new_order = left_sibling.order + 1
    #     # Set instance.order to new_order if this doesn't lead to duplicates; otherwise reorder all siblings
    #     siblings = (instance._meta.model.objects
    #                 .filter(type=instance.type, parent=instance.parent)
    #                 .exclude(id=instance.id))
    #     if siblings.filter(order=new_order).exists():
    #         if left_sibling is None:
    #             left_sibling_seen = True
    #             left_sibling_id = None
    #         else:
    #             left_sibling_seen = False
    #             left_sibling_id = left_sibling.id
    #
    #         for i, child in enumerate(siblings):
    #             child.order = i
    #             if left_sibling_seen:
    #                 child.order += 1
    #             child.save()
    #             if child.id == left_sibling_id:
    #                 left_sibling_seen = True
    #     instance.order = new_order
    #     instance.save()

    def _reorder_descendants(self, node, next_order: int, instance_to_move: M, predecessor) -> int:
        """
        Order descendants of `node` (including `node`) consecutively starting at `next_order` and put
        `instance_to_move` (followed by its descendants) after `predecessor` in the ordering.

        This does not save the instances but instead only sets the fields in the respective element in the dict
        `self._cached_instances`. This dict can be prepared using `self._cache_descendants()`. It can then be used to
        bulk-update the instances.

        Return an order value that can be used for the next node.
        """
        # Make sure that `node` and `instance_to_move` are taken from the cache, otherwise we'll lose the updates
        assert node is self._cached_instances[node.uuid]
        assert instance_to_move is self._cached_instances[instance_to_move.uuid]

        instance_to_move_uuid = instance_to_move.uuid
        predecessor_uuid = predecessor.uuid if predecessor is not None else None

        node.order = next_order
        next_order += 1

        if node.uuid == predecessor_uuid:
            # Put instance_to_move after node (it is either a child or a sibling)
            next_order = self._reorder_descendants(instance_to_move, next_order, instance_to_move, predecessor)

        if hasattr(node, 'children'):
            # We can't use `node.children` because the children might be different due to changes that are only in
            # `self._cached_instances` at this point
            children = [
                n
                for uuid, n in self._cached_instances.items()
                if getattr(n, 'parent', None) == node and uuid != instance_to_move_uuid
            ]
            children = sorted(children, key=lambda child: child.order)  # FIXME: Could be optimized (keep cache sorted)
            for child in children:
                next_order = self._reorder_descendants(child, next_order, instance_to_move, predecessor)
        return next_order

    def _update_tree_position(self, instance, left_sibling_uuid: UUID):
        # When changing the `order` value of instance, we also need to change it for all its descendants, potentially
        # leading to new collisions, so we just reorder everything here

        # Model may or may not have parent field
        parent = getattr(instance, 'parent', None)
        if parent:
            assert parent == self._cached_instances[parent.uuid]
            parent = self._cached_instances[parent.uuid]

        # New predecessor of instance in ordering, not necessarily a sibling of instance
        if left_sibling_uuid is None:
            predecessor = parent
        else:
            left_sibling = self._cached_instances[left_sibling_uuid]
            predecessor = left_sibling

        order = 0
        if left_sibling_uuid is None and parent is None:
            # instance gets order 0
            order = self._reorder_descendants(instance, order, instance, predecessor)

        siblings = [
            node for node in self._cached_instances.values() if node != instance and getattr(node, 'parent', None) == parent
        ]
        siblings = sorted(siblings, key=lambda node: node.order)  # FIXME: Could be optimized (keep cache sorted)
        for node in siblings:
            order = self._reorder_descendants(node, order, instance, predecessor)

        return [('update', instance, ['order']) for instance in self._cached_instances.values()]

    def _cache_descendants(self, node):
        """Add instance `node` and all its descendants to the dict `self._cached_instances`."""
        assert self._cached_instances.get(node.uuid, node) == node
        self._cached_instances[node.uuid] = node
        if hasattr(node, 'children'):
            for child in node.children.all():
                self._cache_descendants(child)


class ActionSerializer(
    ModelWithAttributesSerializerMixin,
    NonTreebeardModelWithTreePositionSerializerMixin[Action],
    BulkSerializerValidationInstanceMixin,
    PlanRelatedModelSerializer[Action],
):
    _modifiable_actions_cache: ActionQuerySet

    uuid = serializers.UUIDField(required=False)
    categories = ActionCategoriesSerializer(required=False)
    responsible_parties = ActionResponsiblePartySerializer(required=False, label=_('Responsible parties'))
    contact_persons = ActionContactPersonSerializer(required=False, label=_('Contact persons'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        must_generate_identifiers = not self.plan.features.has_action_identifiers
        if must_generate_identifiers:
            actions_data = getattr(self, 'initial_data', [])
            if not isinstance(actions_data, list):
                actions_data = [actions_data]
            for action_data in actions_data:
                if not action_data.get('identifier'):
                    # Duplicates Action.generate_identifier, but validation runs before we create an Action instance, so
                    # to avoid an error when we omit an identifier, we need to do it here
                    action_data['identifier'] = generate_identifier(self.plan.actions.all(), 'a', 'identifier')

    def get_fields(self):
        fields = super().get_fields()
        request: Request | None = self.context.get('request')
        user = None
        if request is not None:
            user = user_or_none(request.user)

        if user is None or (not user.is_superuser and not user.is_general_admin_for_plan(self.plan)):
            # Remove fields that are only for admins
            del fields['internal_notes']
            del fields['internal_admin_notes']

        if user is not None:
            fields['modifiable_by_user'] = serializers.SerializerMethodField()

        return fields

    def get_modifiable_by_user(self, action: Action):
        if hasattr(self, '_modifiable_actions_cache'):
            return action in self._modifiable_actions_cache
        request: Request | None = self.context.get('request')
        if request is None:
            return False
        user = user_or_none(request.user)
        view = self.context.get('view')
        if user is None or view is None:
            return False
        self._modifiable_actions_cache = view.get_queryset().modifiable_by(user)
        return action in self._modifiable_actions_cache

    def to_representation(self, value):
        self.context['_current_instance'] = value
        return super().to_representation(value)

    def build_field(self, field_name, info, model_class, nested_depth):
        field_class, field_kwargs = super().build_field(field_name, info, model_class, nested_depth)
        if field_name in ('status', 'implementation_phase', 'decision_level'):
            field_kwargs['queryset'] = field_kwargs['queryset'].filter(plan=self.plan)
        elif field_name == 'primary_org':
            if self.plan.features.has_action_primary_orgs:
                field_kwargs['allow_null'] = False
                field_kwargs['queryset'] = Organization.objects.qs.available_for_plan(self.plan)
            else:
                field_kwargs['queryset'] = Organization.objects.none()

        return field_class, field_kwargs

    def validate_identifier(self, value):
        if not self.plan.features.has_action_identifiers:
            return value

        if not value:
            raise serializers.ValidationError(_('Identifier must be set'))

        qs = self.plan.actions.filter(identifier=value)
        if self._instance is not None:
            qs = qs.exclude(pk=self._instance.pk)
        if qs.exists():
            raise serializers.ValidationError(_('Identifier already exists'))

        self.context.setdefault('seen_identifiers', [])
        if value in self.context['seen_identifiers']:
            raise serializers.ValidationError(_('Identifier already exists'))
        self.context['seen_identifiers'].append(value)
        return value

    def create(self, validated_data: dict):
        validated_data['plan'] = self.plan
        validated_data['order_on_create'] = validated_data.get('order')
        categories = validated_data.pop('categories', None)
        responsible_parties = validated_data.pop('responsible_parties', None)
        contact_persons = validated_data.pop('contact_persons', None)
        instance = super().create(validated_data)
        if categories is not None:
            self.fields['categories'].update(instance, categories)
        if responsible_parties is not None:
            self.fields['responsible_parties'].update(instance, responsible_parties)
        if contact_persons is not None:
            self.fields['contact_persons'].update(instance, contact_persons)
        instance._prefetched_objects_cache = {}
        if self.parent is None:
            self.initialize_cache_context()
        return instance

    def update(self, instance, validated_data):
        categories = validated_data.pop('categories', None)
        responsible_parties = validated_data.pop('responsible_parties', None)
        contact_persons = validated_data.pop('contact_persons', None)
        validated_data.pop('plan', None)
        instance.updated_at = timezone.now()
        instance = super().update(instance, validated_data)
        if categories is not None:
            self.fields['categories'].update(instance, categories)
        if responsible_parties is not None:
            self.fields['responsible_parties'].update(instance, responsible_parties)
        if contact_persons is not None:
            self.fields['contact_persons'].update(instance, contact_persons)
        instance._prefetched_objects_cache = {}
        if self.parent is None:
            self.initialize_cache_context()
        return instance

    class Meta:
        model = Action
        list_serializer_class = BulkListSerializer
        fields = public_fields(
            Action,
            add_fields=[
                'internal_notes',
                'internal_admin_notes',
                'visibility',
                'visibility_display',
            ],
            remove_fields=[
                'impact',
                'status_updates',
                'monitoring_quality_points',
                'image',
                'tasks',
                'links',
                'related_indicators',
                'indicators',
                'impact_groups',
                'merged_actions',
                'superseded_actions',
                'dependent_relationships',
                'copies',
            ],
        )
        read_only_fields = ['plan']


class PlanRelatedSerializer(Protocol):
    kwargs: dict[str, Any]
    get_serializer_context: Callable

    def get_plan(self) -> Plan: ...


class ViewSetWithPlanContext:
    def get_plan(self: PlanRelatedSerializer):
        plan_pk = self.kwargs.get('plan_pk')
        if plan_pk is None:
            return None
        try:
            return Plan.objects.get(pk=plan_pk)
        except Plan.DoesNotExist:
            raise exceptions.NotFound(detail='Plan not found') from None

    def get_serializer_context(self: PlanRelatedSerializer):
        context = super().get_serializer_context()
        plan = self.get_plan()
        if plan is None:
            return context
        context.update({'plan': plan})
        return context


@extend_schema(
    tags=['action'],
)
class ActionViewSet(ViewSetWithPlanContext, HandleProtectedErrorMixin, BulkModelViewSet[Action]):
    serializer_class = ActionSerializer

    def get_permissions(self):
        permission_classes: list[type[permissions.BasePermission]]
        if self.action == 'list':
            permission_classes = [AnonReadOnly]
        else:
            permission_classes = [ActionPermission]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Called during schema generation
            return Action.objects.none()
        plan_pk = self.kwargs['plan_pk']
        plan = PlanViewSet.get_available_plans(request=self.request).filter(id=plan_pk).first()
        if plan is None:
            raise exceptions.NotFound(detail='Plan not found')
        self.plan = plan
        # For caching reasons, we must query the actions through the
        # plan so all of the actions share the same Plan instance
        return plan.actions.all().prefetch_related(
            'schedule',
            'categories',
            'contact_persons',
            'responsible_parties',
            'related_actions',
        )


plan_router.register(
    'actions',
    ActionViewSet,
    basename='action',
)


@register_view
class ActionStatusViewSet(viewsets.ModelViewSet[ActionStatus]):
    queryset = ActionStatus.objects.all()
    serializer_class = ActionStatusSerializer
    filterset_fields = {
        'plan': ('exact',),
        'plan__identifier': ('exact',),
    }


class ActionDecisionLevelSerializer(serializers.HyperlinkedModelSerializer[ActionDecisionLevel]):
    class Meta:
        model = ActionDecisionLevel
        fields = '__all__'


@register_view
class ActionDecisionLevelViewSet(viewsets.ModelViewSet[ActionDecisionLevel]):
    queryset = ActionDecisionLevel.objects.all()
    serializer_class = ActionDecisionLevelSerializer
    filterset_fields = {
        'plan': ('exact',),
        'plan__identifier': ('exact',),
    }


class CategoryTypeSerializer(serializers.HyperlinkedModelSerializer[CategoryType]):
    class Meta:
        model = CategoryType
        fields = '__all__'


class CategoryPermission(permissions.DjangoObjectPermissions):
    # TODO: Refactor duplicated code with ActionPermission, CategoryPermission, OrganizationPermission and PersonPermission
    def check_permission(self, user: User, perm: str, category_type: CategoryType, category: Category | None = None) -> bool:
        # Check for object permissions first
        if not user.has_perms([perm]):
            return False
        if perm == 'actions.change_category':
            if not user.can_modify_category(category=category):
                return False
        elif perm == 'actions.add_category':
            if not user.can_create_category(category_type=category_type):
                return False
        elif perm == 'actions.delete_category':
            if not user.can_delete_category(category_type=category_type):
                return False
        else:
            return False
        return True

    def has_permission(self, request: Request, view) -> bool:
        category_type_pk = view.kwargs.get('category_type_pk')
        if category_type_pk:
            category_type = CategoryType.objects.filter(id=category_type_pk).first()
            if category_type is None:
                raise exceptions.NotFound(detail='Category type not found')
        else:
            category_type = CategoryType.objects.first()
            assert category_type is not None
        if request.method is None:
            return False
        perms = self.get_required_permissions(request.method, Category)
        user = user_or_none(request.user)
        if user is None:
            return False
        return all(self.check_permission(user, perm, category_type) for perm in perms)

    def has_object_permission(self, request: Request, view, obj):
        if request.method is None:
            return False
        perms = self.get_required_object_permissions(request.method, Category)
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        user = user_or_none(request.user)
        if user is None:
            return False
        return all(self.check_permission(user, perm, obj.type, obj) for perm in perms)


class CategoryTypeViewSet(viewsets.ModelViewSet[CategoryType]):
    queryset = CategoryType.objects.all()
    serializer_class = CategoryTypeSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Called during schema generation
            return CategoryType.objects.none()
        plan_pk = self.kwargs['plan_pk']
        plan = PlanViewSet.get_available_plans(request=self.request).filter(id=plan_pk).first()
        if plan is None:
            raise exceptions.NotFound(detail='Plan not found')
        return CategoryType.objects.filter(plan=plan_pk).prefetch_related('categories')


plan_router.register(
    'category-types',
    CategoryTypeViewSet,
    basename='category-type',
)
category_type_router = NestedBulkRouter(plan_router, 'category-types', lookup='category_type')
all_routers.append(category_type_router)


class NonTreebeardParentUUIDField(serializers.Field):
    def get_attribute(self, instance):
        return instance.parent

    def to_representation(self, value):
        if value is None:
            return None
        return str(value.uuid)

    def to_internal_value(self, data):
        return UUID(data)


class CategorySerializer(  # type: ignore[misc]
    ModelWithAttributesSerializerMixin,
    NonTreebeardModelWithTreePositionSerializerMixin[Category],
    BulkSerializerValidationInstanceMixin,
    serializers.ModelSerializer[Category],
):
    parent = NonTreebeardParentUUIDField(allow_null=True, required=False)  # type: ignore[assignment]
    uuid = serializers.UUIDField(required=False)

    def __init__(self, *args, **kwargs):
        # TODO: Refactor duplicated code from aplans.rest_api.PlanRelatedModelSerializer
        self.category_type = kwargs.pop('category_type', None)
        if not self.category_type:
            context = kwargs.get('context')
            if context is not None:
                view = context['view']
                if getattr(view, 'swagger_fake_view', False):
                    # Called during schema generation
                    assert 'category_type_pk' not in view.kwargs
                    self.category_type = CategoryType.objects.first()
                else:
                    category_type_pk = view.kwargs['category_type_pk']
                    category_type = CategoryType.objects.filter(pk=category_type_pk).first()
                    if category_type is None:
                        raise exceptions.NotFound('Category type not found')
                    self.category_type = category_type
            else:
                # Probably called during schema generation
                self.category_type = CategoryType.objects.first()
        super().__init__(*args, **kwargs)

    def create(self, validated_data: dict):
        validated_data['type'] = self.category_type
        validated_data['order_on_create'] = validated_data.get('order')
        if validated_data['parent']:
            validated_data['parent'] = Category.objects.get(uuid=validated_data['parent'])
        instance = super().create(validated_data)
        return instance

    def update(self, instance, validated_data):
        if validated_data['parent']:
            validated_data['parent'] = Category.objects.get(uuid=validated_data['parent'])
        instance = super().update(instance, validated_data)
        # We might want to do some stuff with related objects here
        return instance

    def validate_identifier(self, value):
        if not value:
            raise serializers.ValidationError(_('Identifier must be set'))

        qs = Category.objects.filter(type=self.category_type, identifier=value)
        if self._instance is not None:
            qs = qs.exclude(pk=self._instance.pk)
        if qs.exists():
            raise serializers.ValidationError(_('Identifier already exists'))

        return value

    class Meta:
        model = Category
        list_serializer_class = BulkListSerializer
        fields = public_fields(
            Category,
            remove_fields=['category_pages', 'children', 'indicators', 'level', 'order'],
        )
        read_only_fields = ['type']


@extend_schema(
    # Get rid of some warnings
    parameters=[
        OpenApiParameter(name='plan_id', type=OpenApiTypes.STR, location=OpenApiParameter.PATH),
        OpenApiParameter(name='category_type_id', type=OpenApiTypes.STR, location=OpenApiParameter.PATH),
    ],
)
class CategoryViewSet(ViewSetWithPlanContext, HandleProtectedErrorMixin, BulkModelViewSet):
    serializer_class = CategorySerializer

    def get_permissions(self):
        permission_classes: list[type[permissions.BasePermission]]
        if self.action == 'list':
            permission_classes = [AnonReadOnly]
        else:
            permission_classes = [CategoryPermission]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Called during schema generation
            return Category.objects.none()
        category_type_pk = self.kwargs['category_type_pk']
        return Category.objects.filter(type=category_type_pk).select_related('type')

    def bulk_update(self, request, *args, **kwargs):
        result = super().bulk_update(request, *args, **kwargs)
        post_reorder_categories(sender=None, queryset=self.get_queryset())
        return result


category_type_router.register('categories', CategoryViewSet, basename='category')


class OrganizationPermission(permissions.DjangoObjectPermissions):
    # TODO: Refactor duplicated code with ActionPermission, CategoryPermission, OrganizationPermission and PersonPermission
    def check_permission(self, user: User, perm: str, organization: Organization | None = None):
        # Check for object permissions first
        if not user.has_perms([perm]):
            return False
        if perm == 'orgs.change_organization':
            if not user.can_modify_organization(organization=organization):
                return False
        elif perm == 'orgs.add_organization':
            if not user.can_create_organization():
                return False
        elif perm == 'orgs.delete_organization':
            if not user.can_delete_organization():
                return False
        else:
            return False
        return True

    def has_permission(self, request: Request, view):
        # plan_pk = view.kwargs.get('plan_pk')
        # if plan_pk:
        #     plan = Plan.objects.filter(id=plan_pk).first()
        #     if plan is None:
        #         raise exceptions.NotFound(detail='Plan not found')
        # else:
        #     plan = Plan.objects.live().first()
        if request.method is None:
            return False
        perms = self.get_required_permissions(request.method, Organization)
        user = user_or_none(request.user)
        if user is None:
            return False
        return all(self.check_permission(user, perm) for perm in perms)

    def has_object_permission(self, request, view, obj):
        if request.method is None:
            return False
        perms = self.get_required_object_permissions(request.method, Organization)
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        user = user_or_none(request.user)
        if user is None:
            return False
        return all(self.check_permission(user, perm, obj) for perm in perms)

class OrganizationSerializer(TreebeardModelSerializerMixin[Organization], serializers.ModelSerializer[Organization]):  # type: ignore[misc]
    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = Organization
        list_serializer_class = BulkListSerializer
        fields = public_fields(Organization)

    def create(self, validated_data):
        instance = super().create(validated_data)
        # Add instance to active plan's related organizations
        request = cast('WatchAdminRequest', self.context.get('request'))
        plan = request.get_active_admin_plan()
        plan.related_organizations.add(instance)
        return instance


@register_view
class OrganizationViewSet(HandleProtectedErrorMixin, BulkModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    filterset_fields = {
        'name': ('exact', 'in'),
    }

    # This view set is not registered with a "bulk router" (see BulkRouter or NestedBulkRouter), so we need to define
    # patch and put ourselves
    def patch(self, request, *args, **kwargs):
        return self.partial_bulk_update(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self.bulk_update(request, *args, **kwargs)

    def get_permissions(self):
        permission_classes: list[type[permissions.BasePermission]]
        if self.action == 'list':
            permission_classes = [AnonReadOnly]
        else:
            permission_classes = [OrganizationPermission]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = super().get_queryset()
        plan_identifier = self.request.query_params.get('plan', None)
        if plan_identifier is None:
            return queryset
        try:
            plan = Plan.objects.get(identifier=plan_identifier)
        except Plan.DoesNotExist:
            raise exceptions.NotFound(detail='Plan not found') from None
        return Organization.objects.qs.available_for_plan(plan)



class PersonPermission(permissions.DjangoObjectPermissions):
    # TODO: Refactor duplicated code with ActionPermission, CategoryPermission, OrganizationPermission and PersonPermission
    def check_permission(self, user: User, perm: str, person: Person = None, plan: Plan = None):
        # Check for object permissions first
        if not user.has_perms([perm]):
            return False
        if perm == 'people.change_person':
            if not user.can_modify_person(person=person):
                return False
        elif perm == 'people.add_person':
            if not user.can_create_person():
                return False
        elif perm == 'people.delete_person':
            if person is None:
                #  Does the user have deletion rights in general
                if not user.is_general_admin_for_plan(plan) and not user.is_superuser:
                    return False
            # Does the user have deletion rights to this person in this plan
            elif not user.can_edit_or_delete_person_within_plan(person, plan=plan):
                return False
        else:
            return False
        return True

    def has_permission(self, request: Request, view):
        if request.method is None:
            return False
        perms = self.get_required_permissions(request.method, Person)
        plan = request.get_active_admin_plan()
        user = user_or_none(request.user)
        if user is None:
            return False
        return all(self.check_permission(user, perm, plan=plan) for perm in perms)

    def has_object_permission(self, request, view, obj):
        if request.method is None:
            return False
        perms = self.get_required_object_permissions(request.method, Person)
        plan = request.get_active_admin_plan()
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        user = user_or_none(request.user)
        if user is None:
            return False
        return all(self.check_permission(user, perm, person=obj, plan=plan) for perm in perms)

class PersonSerializer(BasePersonSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.context.get('authorized_for_plan') is None:
            self.fields.pop('email')

@register_view
class PersonViewSet(ModelWithImageViewMixin, BulkModelViewSet[Person]):
    queryset = Person.objects.get_queryset()
    serializer_class = PersonSerializer

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # This view set is not registered with a "bulk router" (see BulkRouter or NestedBulkRouter), so we need to define
    # patch and put ourselves
    def patch(self, request, *args, **kwargs):
        return self.partial_bulk_update(request, *args, **kwargs)

    def put(self, request, *args, **kwargs):
        return self.bulk_update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        # FIXME: Duplicated in people.wagtail_admin.PersonDeleteView.delete_instance()
        acting_admin_user = self.request.user
        instance.delete_and_deactivate_corresponding_user(acting_admin_user)

    def get_permissions(self):
        permission_classes: list[type[permissions.BasePermission]]
        if self.action == 'list':
            permission_classes = [AnonReadOnly]
        else:
            permission_classes = [PersonPermission]
        return [permission() for permission in permission_classes]

    def get_plan(self):
        plan_identifier = self.request.query_params.get('plan', None)
        if plan_identifier is None:
            return None
        try:
            return Plan.objects.get(identifier=plan_identifier)
        except Plan.DoesNotExist:
            raise exceptions.NotFound(detail='Plan not found') from None

    def user_is_authorized_for_plan(self, plan: Plan):
        user = user_or_none(self.request.user)
        return (
            user is not None
            and user.is_authenticated
            and (
                user.is_general_admin_for_plan(plan)
                or user.is_contact_person_in_plan(plan)
            )
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        plan = self.get_plan()
        if plan is None:
            return context
        if self.user_is_authorized_for_plan(plan):
            context.update({'authorized_for_plan': plan})
        return context

    def get_queryset(self):
        queryset = cast('PersonQuerySet', super().get_queryset())
        plan = self.get_plan()
        if plan is None:
            return queryset
        if not self.user_is_authorized_for_plan(plan):
            raise exceptions.PermissionDenied(detail='Not authorized')
        return queryset.available_for_plan(plan, include_contact_persons=True)


# FIXME: This is very similar to kausal_common.datasets.api.I18nFieldSerializerMixin
class I18nFieldPlanLanguagesSerializerMixin:
    """
    Add fields for translated strings to serializers whose context contains a plan.

    This adds a field `<field>_<lang>` for every translatable field `<field>` and every language `<lang>` supported by
    the plan except the primary language (for which there is `<field>`).
    """

    context: dict[str, Any]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        i18n_field = get_i18n_field(self.Meta.model)  # type: ignore[attr-defined]
        if not i18n_field:
            return
        plan = self.context.get('plan')
        if getattr(self.context.get('view'), 'swagger_fake_view', False):
            # Called during schema generation
            assert not plan
            # Add field with language suffix for every language known to this app
            languages = get_available_languages()
        else:
            assert isinstance(plan, Plan)
            # Add field with language suffix for every non-primary language supported by the plan
            languages = plan.other_languages
        for source_field in i18n_field.fields:
            if source_field not in self.Meta.fields:  # type: ignore[attr-defined]
                continue
            for lang in languages:
                translated_field = build_localized_fieldname(source_field, lang)
                self.fields[translated_field] = serializers.CharField(  # type: ignore[attr-defined]
                    required=False,
                )


class ActionTaskSerializer(I18nFieldPlanLanguagesSerializerMixin, serializers.ModelSerializer):
    """Serializer for the ActionTask model."""

    class Meta:
        model = ActionTask
        list_serializer_class = BulkListSerializer
        fields = public_fields(ActionTask)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        plan = self.context.get('plan')
        action_field = self.fields.get('action')
        if plan and action_field:
            assert isinstance(action_field, RelatedField)
            action_field.queryset = Action.objects.filter(plan=plan)


class ActionTaskViewSet(ViewSetWithPlanContext, BulkModelViewSet[ActionTask]):
    queryset = ActionTask.objects.all()
    serializer_class = ActionTaskSerializer

    def get_permissions(self):
        permission_classes: list[type[permissions.BasePermission]]
        if self.action == 'list':
            permission_classes = [AnonReadOnly]
        else:
            permission_classes = [ActionTaskPermission]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Called during schema generation
            return ActionTask.objects.none()
        plan_pk = self.kwargs['plan_pk']
        plan = PlanViewSet.get_available_plans(request=self.request).filter(id=plan_pk).first()
        if plan is None:
            raise exceptions.NotFound(detail='Plan not found')
        qs = ActionTask.objects.filter(action__plan=plan_pk)
        action_id = self.request.query_params.get('action')
        if action_id:
            qs = qs.filter(action_id=action_id)
        return qs


plan_router.register(
    'action-tasks',
    ActionTaskViewSet,
    basename='action-task',
)
action_task_router = NestedBulkRouter(plan_router, 'action-tasks', lookup='action_task')
all_routers.append(action_task_router)


class ActionTaskPermission(permissions.DjangoObjectPermissions):
    def check_permission(self, user: User, perm: str, plan: Plan, task: ActionTask | None = None):
        # Check for object permissions first
        if not user.has_perms([perm]):
            return False
        if task:
            action = task.action
        else:
            action = None
        if perm in (f'actions.{op}_actiontask' for op in ('change', 'add', 'delete')):
            if not user.can_modify_action(action=action, plan=plan):
                return False
        else:
            return False
        return True

    def has_permission(self, request: Request, view):
        plan_pk = view.kwargs.get('plan_pk')
        if plan_pk:
            plan = Plan.objects.filter(id=plan_pk).first()
            if plan is None:
                raise exceptions.NotFound(detail='Plan not found')
        else:
            plan = Plan.objects.get_queryset().live().first()
            assert plan is not None
        if request.method is None:
            return False
        perms = self.get_required_permissions(request.method, ActionTask)
        user = user_or_none(request.user)
        if user is None:
            return False
        return all(self.check_permission(user, perm, plan) for perm in perms)

    def has_object_permission(self, request, view, obj):
        if request.method is None:
            return False
        perms = self.get_required_object_permissions(request.method, ActionTask)
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        user = user_or_none(request.user)
        if user is None:
            return False
        return all(self.check_permission(user, perm, obj.action.plan, obj) for perm in perms)


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
