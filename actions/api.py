from __future__ import annotations

import copy
import rest_framework.fields
import typing
from collections import Counter
from typing import Optional
from uuid import UUID

from django.core.exceptions import FieldDoesNotExist
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Model
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from rest_framework import exceptions, permissions, serializers, viewsets

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, extend_schema_field, OpenApiParameter
from rest_framework_nested import routers

from actions.models.action import ActionImplementationPhase, ActionContactPerson
from actions.models.attributes import AttributeType
from actions.models.plan import PlanQuerySet
from aplans.api_router import router
from aplans.model_images import (
    ModelWithImageSerializerMixin, ModelWithImageViewMixin
)
from aplans.permissions import AnonReadOnly
from aplans.rest_api import (
    BulkListSerializer, BulkModelViewSet, HandleProtectedErrorMixin, PlanRelatedModelSerializer
)
from aplans.types import AuthenticatedWatchRequest, WatchAdminRequest, WatchAPIRequest
from aplans.utils import generate_identifier, public_fields, register_view_helper
from orgs.models import Organization
from people.models import Person
from users.models import User

from .models import (
    Action, ActionDecisionLevel, ActionImpact, ActionResponsibleParty, ActionSchedule, ActionStatus,
    ActionTask, Category, CategoryType, ImpactGroup, ImpactGroupAction, Plan,
    Scenario
)

if typing.TYPE_CHECKING:
    from django.db.models import QuerySet  # noqa

all_views = []
all_routers = []


def register_view(klass, *args, **kwargs):
    return register_view_helper(all_views, klass, *args, **kwargs)


class BulkRouter(routers.SimpleRouter):
    routes = copy.deepcopy(routers.SimpleRouter.routes)
    routes[0].mapping.update({
        'put': 'bulk_update',
        'patch': 'partial_bulk_update',
    })


class NestedBulkRouter(routers.NestedDefaultRouter, BulkRouter):
    pass


class BulkSerializerValidationInstanceMixin:
    def run_validation(self, data: dict):
        if self.parent and self.instance is not None:
            assert isinstance(self.instance, models.query.QuerySet)
            self._instance = self.instance.get(id=data['id'])
        else:
            self._instance = self.instance
        return super().run_validation(data)


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
                'monitoring_quality_points', 'action_impacts', 'superseded_plans',
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

    request: WatchAPIRequest

    @classmethod
    def get_available_plans(
        cls, queryset: Optional[PlanQuerySet] = None, request: Optional[WatchAPIRequest] = None
    ) -> PlanQuerySet:
        user: Optional[User]
        if not request or not request.user or not request.user.is_authenticated:
            user = None
        else:
            assert isinstance(request.user, User)
            user = request.user

        if queryset is None:
            queryset = Plan.objects.all()  # type: ignore
            assert queryset is not None

        if user is not None:
            return queryset.live() | queryset.filter(id__in=user.get_adminable_plans())
        return queryset.live()

    @classmethod
    def get_default_plan(
        cls, queryset: Optional[PlanQuerySet] = None, request: Optional[WatchAPIRequest] = None
    ) -> Plan:
        plans = cls.get_available_plans(queryset=queryset, request=request)
        plan = None
        if request is not None:
            if hasattr(request, 'get_active_admin_plan'):
                admin_plan = request.get_active_admin_plan()
                plan = plans.filter(id=admin_plan.id).first()

        if plan is None:
            plan = plans.first()
        assert plan is not None
        return plan

    def get_queryset(self) -> PlanQuerySet:
        qs = super().get_queryset()
        return self.get_available_plans(qs, self.request)


router.register('plan', PlanViewSet, basename='plan')
plan_router = NestedBulkRouter(router, 'plan', lookup='plan')
all_routers.append(plan_router)


class ActionScheduleViewSet(viewsets.ModelViewSet):
    serializer_class = ActionScheduleSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Called during schema generation
            return ActionSchedule.objects.none()
        return ActionSchedule.objects.filter(plan=self.kwargs['plan_pk'])


plan_router.register(
    'action_schedules', ActionScheduleViewSet, basename='action_schedule',
)


class ActionImplementationPhaseViewSet(viewsets.ModelViewSet):
    serializer_class = ActionImplementationPhaseSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Called during schema generation
            return ActionImplementationPhase.objects.none()
        return ActionImplementationPhase.objects.filter(plan=self.kwargs['plan_pk'])


plan_router.register(
    'action_implementation_phases', ActionImplementationPhaseViewSet, basename='action_implementation_phase',
)


class ActionPermission(permissions.DjangoObjectPermissions):
    # TODO: Refactor duplicated code with ActionPermission, CategoryPermission, OrganizationPermission and PersonPermission
    def check_permission(self, user: User, perm: str, plan: Plan, action: Action = None):
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

    def has_permission(self, request: AuthenticatedWatchRequest, view):
        plan_pk = view.kwargs.get('plan_pk')
        if plan_pk:
            plan = Plan.objects.filter(id=plan_pk).first()
            if plan is None:
                raise exceptions.NotFound(detail='Plan not found')
        else:
            plan = Plan.objects.live().first()
        perms = self.get_required_permissions(request.method, Action)
        for perm in perms:
            if not self.check_permission(request.user, perm, plan):
                return False
        return True

    def has_object_permission(self, request, view, obj):
        perms = self.get_required_object_permissions(request.method, Action)
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        for perm in perms:
            if not self.check_permission(request.user, perm, obj.plan, obj):
                return False
        return True


@extend_schema_field(dict(
    type='object',
    additionalProperties=dict(
        type='array',
        title='categories',
        items=dict(type='integer'),
    )
))
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

    def set_instance_values(self, data):
        raise NotImplementedError()

    def get_multiple_error(self):
        raise NotImplementedError()

    def to_representation(self, value):
        key = self.get_type_label()
        fk_id_label = f'{key}_id'
        return [{
            key: getattr(v, fk_id_label),
            'role': v.role,
        } for v in value.all()]

    def to_internal_value(self, data):
        s = self.parent
        plan: Plan = s.plan
        if not isinstance(data, list):
            raise exceptions.ValidationError('expecting a list')
        available_instances = {x for x in self.get_available_instances(plan).values_list('id', flat=True)}
        seen_instances = set()
        key = self.get_type_label()

        for val in data:
            instance_id = val.get(key, None)
            role = val.get('role', None)
            if not (isinstance(val, dict)
                    and isinstance(instance_id, int)
                    and (role is None or isinstance(role, str))):
                raise exceptions.ValidationError(
                    'expecting a list of dicts mapping "organization" to int and "role" to str or None'
                )
            if val[key] not in available_instances:
                raise exceptions.ValidationError('%d not available for plan' % val[key])
            if val['role'] not in self.get_allowed_roles():
                raise exceptions.ValidationError(f"{val['role']} is not a valid role")
            if instance_id in seen_instances:
                raise exceptions.ValidationError(self.get_multiple_error())
            seen_instances.add(instance_id)
            val[key] = self.get_queryset().get(id=instance_id)
        return data

    def update(self, instance: Action, validated_data):
        assert isinstance(instance, Action)
        assert instance.pk is not None
        self.set_instance_values(instance, validated_data)


@extend_schema_field(dict(
    type='object',
    title=_('Responsible parties'),
))
class ActionResponsiblePartySerializer(ActionResponsibleWithRoleSerializer):
    def get_type_label(self):
        return 'organization'

    def get_available_instances(self, plan) -> QuerySet:
        return Organization.objects.available_for_plan(plan)

    def get_allowed_roles(self):
        return ActionResponsibleParty.Role.values

    def get_queryset(self):
        return Organization.objects.all()

    def set_instance_values(self, instance, data):
        instance.set_responsible_parties(data)

    def get_multiple_error(self):
        return _("Organization occurs multiple times as responsible party")


@extend_schema_field(dict(
    type='object',
    title=_('Contact persons'),
))
class ActionContactPersonSerializer(ActionResponsibleWithRoleSerializer):
    def get_type_label(self):
        return 'person'

    def get_available_instances(self, plan) -> QuerySet:
        return Person.objects.available_for_plan(plan)

    def get_allowed_roles(self):
        return ActionContactPerson.Role.values

    def get_queryset(self):
        return Person.objects.all()

    def set_instance_values(self, instance, data):
        instance.set_contact_persons(data)

    def get_multiple_error(self):
        return _("Person occurs multiple times as contact person")


class AttributesSerializerMixin:
    # In the serializer, set `attribute_format` to a value from `AttributeType.AttributeFormat`
    def get_fields(self):
        fields = super().get_fields()
        request = self.context.get('request')
        if request is not None and request.user and request.user.is_authenticated:
            user = request.user
            plan = user.get_active_admin_plan()
            attribute_types = plan.action_attribute_types.filter(format=self.attribute_format)
            for attribute_type in attribute_types:
                instances_editable = attribute_type.are_instances_editable_by(user, plan)
                fields[attribute_type.identifier] = rest_framework.fields.FloatField(
                    label=attribute_type.name,
                    read_only=not instances_editable,
                )
        return fields

    def get_cached_values(self):
        if '_cache' not in self.context or '_current_instance' not in self.context:
            return None
        # I was unable to access the individual serializable instance through serializer or its parents when serializing with a
        # listserializer. Hence, the need to store the instance in the context
        instance_pk = self.context['_current_instance'].pk
        attributes = self.context['_cache'].get(self.attribute_format, {})
        return attributes.get(instance_pk, [])


class ChoiceAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_format = AttributeType.AttributeFormat.ORDERED_CHOICE

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {v.type.identifier: v.choice_id for v in values}

    def to_internal_value(self, data):
        return data

    def update(self, instance: Action, validated_data):
        assert instance.pk is not None
        for attribute_type_identifier, choice_id in validated_data.items():
            instance.set_choice_attribute(attribute_type_identifier, choice_id)


class ChoiceWithTextAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_format = AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {v.type.identifier: {'choice': v.choice_id, 'text': v.text} for v in values}

    def to_internal_value(self, data):
        return data

    def update(self, instance: Action, validated_data):
        assert instance.pk is not None
        for attribute_type_identifier, item in validated_data.items():
            instance.set_choice_with_text_attribute(attribute_type_identifier, item.get('choice'), item.get('text'))


class NumericValueAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_format = AttributeType.AttributeFormat.NUMERIC

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {v.type.identifier: v.value for v in values}

    def to_internal_value(self, data):
        return data

    def update(self, instance: Action, validated_data):
        assert instance.pk is not None
        for attribute_type_identifier, value in validated_data.items():
            instance.set_numeric_value_attribute(attribute_type_identifier, value)


class TextAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_format = AttributeType.AttributeFormat.TEXT

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {v.type.identifier: v.text for v in values}

    def to_internal_value(self, data):
        return data

    def update(self, instance: Action, validated_data):
        assert instance.pk is not None
        for attribute_type_identifier, value in validated_data.items():
            instance.set_text_attribute(attribute_type_identifier, value)


class RichTextAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_format = AttributeType.AttributeFormat.RICH_TEXT

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {v.type.identifier: v.text for v in values}

    def to_internal_value(self, data):
        return data

    def update(self, instance: Action, validated_data):
        assert instance.pk is not None
        for attribute_type_identifier, value in validated_data.items():
            instance.set_rich_text_attribute(attribute_type_identifier, value)


class CategoryChoiceAttributesSerializer(AttributesSerializerMixin, serializers.Serializer):
    attribute_format = AttributeType.AttributeFormat.CATEGORY_CHOICE

    def to_representation(self, value):
        cached = self.get_cached_values()
        values = cached if cached is not None else value.all()
        return {v.type.identifier: [cat.id for cat in v.categories.all()] for v in values}

    def to_internal_value(self, data):
        return data

    def update(self, instance: Action, validated_data):
        assert instance.pk is not None
        for attribute_type_identifier, category_ids in validated_data.items():
            instance.set_category_choice_attribute(attribute_type_identifier, category_ids)


# Regarding the metaclass: https://stackoverflow.com/a/58304791/14595546
class ModelWithAttributesSerializerMixin(metaclass=serializers.SerializerMetaclass):
    choice_attributes = ChoiceAttributesSerializer(required=False)
    choice_with_text_attributes = ChoiceWithTextAttributesSerializer(required=False)
    numeric_value_attributes = NumericValueAttributesSerializer(required=False)
    text_attributes = TextAttributesSerializer(required=False)
    rich_text_attributes = RichTextAttributesSerializer(required=False)
    category_choice_attributes = CategoryChoiceAttributesSerializer(required=False)

    _attribute_fields = [
        'choice_attributes', 'choice_with_text_attributes', 'numeric_value_attributes', 'text_attributes',
        'rich_text_attributes', 'category_choice_attributes',
    ]

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

    def _update_attribute_fields(self, instance, popped_fields):
        for field_name, data in popped_fields.items():
            if data is not None:
                self.fields[field_name].update(instance, data)


class PrevSiblingField(serializers.CharField):
    # Instances must implement method get_prev_sibling(). (Treebeard nodes do that.) Must be used in ModelSerializer so
    # we can get the model for to_internal_value().
    # FIXME: This is ugly.
    def get_attribute(self, instance):
        return instance.get_prev_sibling()

    def to_representation(self, value):
        # value is the left sibling of the original instance
        if value is None:
            return None
        try:
            value._meta.get_field('uuid')
            return value.uuid
        except FieldDoesNotExist:
            return value.id

    def to_internal_value(self, data):
        # FIXME: No validation (e.g., permission checking)
        model = self.parent.Meta.model
        # We use a UUID as the value for this field if the model has a field called uuid. Otherwise we use the
        # related model instance itself.
        try:
            model._meta.get_field('uuid')
            return UUID(data)
        except FieldDoesNotExist:
            return model.objects.get(id=data)


# Regarding the metaclass: https://stackoverflow.com/a/58304791/14595546
class NonTreebeardModelWithTreePositionSerializerMixin(metaclass=serializers.SerializerMetaclass):
    left_sibling = PrevSiblingField(allow_null=True, required=False)

    def get_field_names(self, declared_fields, info):
        fields = super().get_field_names(declared_fields, info)
        # fields += self._tree_position_fields
        fields.append('left_sibling')
        return fields

    def create(self, validated_data: dict):
        left_sibling_uuid = validated_data.pop('left_sibling', None)
        instance = super().create(validated_data)
        if left_sibling_uuid is None:
            left_sibling = None
        else:
            left_sibling = self.Meta.model.objects.get(uuid=left_sibling_uuid)
        self._update_tree_position(instance, left_sibling)
        return instance

    def update(self, instance, validated_data):
        # FIXME: Since left_sibling has allow_null=True, we should distinguish whether left_sibling is None because it
        # is not in validated_data or because validated_data['left_sibling'] is None. Sending a PUT request and omitting
        # left_sibling might inadvertently move the node.
        left_sibling_uuid = validated_data.pop('left_sibling', None)
        instance = super().update(instance, validated_data)
        if left_sibling_uuid is None:
            left_sibling = None
        else:
            left_sibling = self.Meta.model.objects.get(uuid=left_sibling_uuid)
        self._update_tree_position(instance, left_sibling)
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

    def _reorder_descendants(self, node, next_order, instance_to_move, predecessor):
        """
        Order descendants of `node` (including `node`) consecutively starting at `next_order` and put
        `instance_to_move` (followed by its descendants) after `predecessor` in the ordering.

        This does not save the instances but instead only sets the fields in the respective element in the dict
        `self._cached_instances`. This dict can be prepared using `self._cache_descendants()`. It can then be used to
        bulk-update the instances.

        Return an order value that can be used for the next node.
        """
        # Make sure that `node` and `instance_to_move` are taken from the cache, otherwise we'll lose the updates
        assert node is self._cached_instances[node.id]
        assert instance_to_move is self._cached_instances[instance_to_move.id]

        instance_to_move_id = getattr(instance_to_move, 'id', None)
        predecessor_id = getattr(predecessor, 'id', None)

        node.order = next_order
        next_order += 1

        if node.id == predecessor_id:
            # Put instance_to_move after node (it is either a child or a sibling)
            next_order = self._reorder_descendants(instance_to_move, next_order, instance_to_move, predecessor)

        if hasattr(node, 'children'):
            for child_id in node.children.exclude(id=instance_to_move_id).values_list('id', flat=True):
                child = self._cached_instances[child_id]
                next_order = self._reorder_descendants(child, next_order, instance_to_move, predecessor)
        return next_order

    def _update_tree_position(self, instance, left_sibling):
        # When changing the `order` value of instance, we also need to change it for all its descendants, potentially
        # leading to new collisions, so we just reorder everything here

        # Model may or may not have parent field
        parent = getattr(instance, 'parent', None)

        # New predecessor of instance in ordering, not necessarily a sibling of instance
        if left_sibling is None:
            predecessor = parent
        else:
            predecessor = left_sibling

        # Use instance cache for bulk update
        self._cached_instances = {}
        for node in instance.get_siblings():
            self._cache_descendants(node)
        instance = self._cached_instances[instance.id]

        order = 0
        if left_sibling is None and parent is None:
            # instance gets order 0
            order = self._reorder_descendants(instance, order, instance, predecessor)

        for node_id in instance.get_siblings().exclude(id=instance.id).values_list('id', flat=True):
            node = self._cached_instances[node_id]
            order = self._reorder_descendants(node, order, instance, predecessor)

        self.Meta.model.objects.bulk_update(self._cached_instances.values(), ['order'])

    def _cache_descendants(self, node):
        """Add instance `node` and all its descendants to the dict `self._cached_instances`."""
        assert node.id not in self._cached_instances
        self._cached_instances[node.id] = node
        if hasattr(node, 'children'):
            for child in node.children.all():
                self._cache_descendants(child)


class ActionSerializer(
    ModelWithAttributesSerializerMixin,
    NonTreebeardModelWithTreePositionSerializerMixin,
    BulkSerializerValidationInstanceMixin,
    PlanRelatedModelSerializer,
):
    uuid = serializers.UUIDField(required=False)
    categories = ActionCategoriesSerializer(required=False)
    responsible_parties = ActionResponsiblePartySerializer(required=False, label=_('Responsible parties'))
    contact_persons = ActionContactPersonSerializer(required=False, label=_('Contact persons'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initialize_cache_context(self.instance, self.plan)
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

    def initialize_cache_context(self, instance: Model | list[Model], plan: Plan):
        if instance is None or 'request' not in self.context:
            return
        if isinstance(instance, list):
            instance = instance[0]
        request = self.context['request']
        user = request.user
        attribute_types = instance.get_editable_attribute_types(user)
        prepopulated_attributes = {}
        action_content_type = ContentType.objects.get_for_model(instance)
        for at in attribute_types:
            prepopulated_attributes.setdefault(at.instance.format, {})
            for a in at.attributes.filter(content_type=action_content_type):
                prepopulated_attributes[at.instance.format].setdefault(a.object_id, []).append(a)

        for field_name in self._attribute_fields:
            self.fields[field_name].context['_cache'] = prepopulated_attributes

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

    def to_representation(self, value):
        self.context['_current_instance'] = value
        return super().to_representation(value)

    def build_field(self, field_name, info, model_class, nested_depth):
        field_class, field_kwargs = super().build_field(field_name, info, model_class, nested_depth)
        if field_name in ('status', 'implementation_phase', 'decision_level', 'schedule'):
            field_kwargs['queryset'] = field_kwargs['queryset'].filter(plan=self.plan)
        elif field_name == 'primary_org':
            if self.plan.features.has_action_primary_orgs:
                field_kwargs['allow_null'] = False
                field_kwargs['queryset'] = Organization.objects.available_for_plan(self.plan)
            else:
                field_kwargs['queryset'] = Organization.objects.none()
        elif field_name == 'related_actions':
            related_plans = self.plan.get_all_related_plans(inclusive=True)
            field_kwargs['queryset'] = field_kwargs['queryset'].filter(plan__in=related_plans)

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
        return instance

    class Meta:
        model = Action
        list_serializer_class = BulkListSerializer
        fields = public_fields(
            Action,
            add_fields=[
                'internal_notes', 'internal_admin_notes',
            ],
            remove_fields=[
                'impact',
                'status_updates', 'monitoring_quality_points', 'image',
                'tasks', 'links', 'related_indicators', 'indicators',
                'impact_groups', 'merged_actions', 'superseded_actions',
            ]
        )
        read_only_fields = ['plan']


@extend_schema(
    tags=['action']
)
class ActionViewSet(HandleProtectedErrorMixin, BulkModelViewSet):
    serializer_class = ActionSerializer

    def get_permissions(self):
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
            raise exceptions.NotFound(detail="Plan not found")
        self.plan = plan
        # For caching reasons, we must query the actions through the
        # plan so all of the actions share the same Plan instance
        return plan.actions.all().prefetch_related(
            'schedule', 'categories', 'contact_persons', 'responsible_parties', 'related_actions'
        )


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


class CategoryPermission(permissions.DjangoObjectPermissions):
    # TODO: Refactor duplicated code with ActionPermission, CategoryPermission, OrganizationPermission and PersonPermission
    def check_permission(self, user: User, perm: str, category_type: CategoryType, category: Category = None):
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

    def has_permission(self, request: AuthenticatedWatchRequest, view):
        category_type_pk = view.kwargs.get('category_type_pk')
        if category_type_pk:
            category_type = CategoryType.objects.filter(id=category_type_pk).first()
            if category_type is None:
                raise exceptions.NotFound(detail='Category type not found')
        else:
            category_type = CategoryType.objects.live().first()
        perms = self.get_required_permissions(request.method, Category)
        for perm in perms:
            if not self.check_permission(request.user, perm, category_type):
                return False
        return True

    def has_object_permission(self, request, view, obj):
        perms = self.get_required_object_permissions(request.method, Category)
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        for perm in perms:
            if not self.check_permission(request.user, perm, obj.type, obj):
                return False
        return True


class CategoryTypeViewSet(viewsets.ModelViewSet):
    queryset = CategoryType.objects.all()
    serializer_class = CategoryTypeSerializer

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Called during schema generation
            return CategoryType.objects.none()
        plan_pk = self.kwargs['plan_pk']
        plan = PlanViewSet.get_available_plans(request=self.request).filter(id=plan_pk).first()
        if plan is None:
            raise exceptions.NotFound(detail="Plan not found")
        return CategoryType.objects.filter(plan=plan_pk)\
            .prefetch_related('categories')


plan_router.register(
    'category-types', CategoryTypeViewSet, basename='category-type',
)
category_type_router = NestedBulkRouter(plan_router, 'category-types', lookup='category_type')
all_routers.append(category_type_router)


class NonTreebeardParentUUIDField(serializers.Field):
    def get_attribute(self, instance):
        return instance.parent

    def to_representation(self, value):
        if value is None:
            return None
        return value.uuid

    def to_internal_value(self, data):
        return data


class CategorySerializer(
    ModelWithAttributesSerializerMixin,
    NonTreebeardModelWithTreePositionSerializerMixin,
    BulkSerializerValidationInstanceMixin,
    serializers.ModelSerializer,
):
    parent = NonTreebeardParentUUIDField(allow_null=True, required=False)
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
            raise serializers.ValidationError(_("Identifier must be set"))

        qs = Category.objects.filter(type=self.category_type, identifier=value)
        if self._instance is not None:
            qs = qs.exclude(pk=self._instance.pk)
        if qs.exists():
            raise serializers.ValidationError(_("Identifier already exists"))

        return value

    class Meta:
        model = Category
        list_serializer_class = BulkListSerializer
        fields = public_fields(
            Category,
            remove_fields=['category_pages', 'children', 'indicators', 'level', 'order']
        )
        read_only_fields = ['type']


@extend_schema(
    # Get rid of some warnings
    parameters=[
        OpenApiParameter(name='plan_id', type=OpenApiTypes.STR, location=OpenApiParameter.PATH),
        OpenApiParameter(name='category_type_id', type=OpenApiTypes.STR, location=OpenApiParameter.PATH),
    ],
)
class CategoryViewSet(HandleProtectedErrorMixin, BulkModelViewSet):
    serializer_class = CategorySerializer

    def get_permissions(self):
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
        return Category.objects.filter(type=category_type_pk)


category_type_router.register('categories', CategoryViewSet, basename='category')


class OrganizationPermission(permissions.DjangoObjectPermissions):
    # TODO: Refactor duplicated code with ActionPermission, CategoryPermission, OrganizationPermission and PersonPermission
    def check_permission(self, user: User, perm: str, organization: Organization = None):
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

    def has_permission(self, request: AuthenticatedWatchRequest, view):
        # plan_pk = view.kwargs.get('plan_pk')
        # if plan_pk:
        #     plan = Plan.objects.filter(id=plan_pk).first()
        #     if plan is None:
        #         raise exceptions.NotFound(detail='Plan not found')
        # else:
        #     plan = Plan.objects.live().first()
        perms = self.get_required_permissions(request.method, Organization)
        for perm in perms:
            if not self.check_permission(request.user, perm):
                return False
        return True

    def has_object_permission(self, request, view, obj):
        perms = self.get_required_object_permissions(request.method, Organization)
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        for perm in perms:
            if not self.check_permission(request.user, perm, obj):
                return False
        return True


class TreebeardParentField(serializers.CharField):
    # For serializers of Treebeard node models
    def get_attribute(self, instance):
        return instance.get_parent()

    def to_representation(self, value):
        # value is the parent of the original instance
        if value is None:
            return None
        try:
            value._meta.get_field('uuid')
            return value.uuid
        except FieldDoesNotExist:
            return value.id

    def to_internal_value(self, data):
        # FIXME: No validation (e.g., permission checking)
        model = self.parent.Meta.model
        # We use a UUID as the value for this field if the model has a field called uuid. Otherwise we use the
        # related model instance itself.
        try:
            model._meta.get_field('uuid')
            return UUID(data)
        except FieldDoesNotExist:
            return model.objects.get(id=data)


# Regarding the metaclass: https://stackoverflow.com/a/58304791/14595546
class TreebeardModelSerializerMixin(metaclass=serializers.SerializerMetaclass):
    parent = TreebeardParentField(allow_null=True, required=False)
    left_sibling = PrevSiblingField(allow_null=True, required=False)

    def get_field_names(self, declared_fields, info):
        fields = super().get_field_names(declared_fields, info)
        fields += ['parent', 'left_sibling']
        return fields

    def _get_instance_from_uuid(self, uuid):
        if uuid is None:
            return None
        return self.Meta.model.objects.get(uuid=uuid)

    def _get_validated_instance_data(self, uuid):
        for child_data in getattr(self.parent, '_children_validated_so_far', []):
            if child_data['uuid'] == uuid:
                return child_data
        raise exceptions.ValidationError("No validated instance with the given UUID found")

    def run_validation(self, *args, **kwargs):
        data = super().run_validation(*args, **kwargs)
        if hasattr(self.parent, '_children_validated_so_far'):
            self.parent._children_validated_so_far.append(data)
        return data

    def validate(self, data):
        # Map UUID to UUID
        if data['left_sibling']:
            parents = {data['uuid']: data['parent'] for data in self.initial_data}
            if data['left_sibling'] in parents:
                left_sibling_parent_uuid = parents[data['left_sibling']]
            else:
                try:
                    left_sibling = self._get_instance_from_uuid(data['left_sibling'])
                except self.Meta.model.DoesNotExist:
                    # Maybe the instance is not created yet because it is about to be created in the same request
                    left_sibling = self._get_validated_instance_data(data['left_sibling'])
                    left_sibling_parent_uuid = left_sibling['parent']
                else:
                    assert left_sibling is not None
                    if left_sibling.parent is None:
                        left_sibling_parent_uuid = None
                    else:
                        left_sibling_parent_uuid = left_sibling.parent.uuid
            if left_sibling_parent_uuid != data['parent']:
                raise exceptions.ValidationError("Instance and left sibling have different parents")
        return data

    def create(self, validated_data):
        parent_uuid = validated_data.pop('parent', None)
        parent = self._get_instance_from_uuid(parent_uuid)
        left_sibling_uuid = validated_data.pop('left_sibling', None)
        left_sibling = self._get_instance_from_uuid(left_sibling_uuid)
        instance = Organization(**validated_data)
        # This sucks, but I don't think Treebeard provides an easier way of doing this
        if left_sibling is None:
            if parent is None:
                first_root = Organization.get_first_root_node()
                if first_root is None:
                    Organization.add_root(instance=instance)
                else:
                    first_root.add_sibling('left', instance=instance)
            else:
                right_sibling = parent.get_first_child()
                if right_sibling is None:
                    parent.add_child(instance=instance)
                else:
                    right_sibling.add_sibling('left', instance=instance)
        else:
            left_sibling.add_sibling('right', instance=instance)
        return instance

    def update(self, instance, validated_data):
        # FIXME: Since left_sibling has allow_null=True, we should distinguish whether left_sibling is None because it
        # is not in validated_data or because validated_data['left_sibling'] is None. Similarly for parent. Sending a
        # PUT request and omitting one of these fields might inadvertently move the node.
        parent_uuid = validated_data.pop('parent', None)
        parent = self._get_instance_from_uuid(parent_uuid)
        left_sibling_uuid = validated_data.pop('left_sibling', None)
        left_sibling = self._get_instance_from_uuid(left_sibling_uuid)
        # If this is called from BulkListSerializer, then `instance` might be in some weird state and if we don't
        # re-fetch it we'll get weird integrity errors.
        instance = instance._meta.model.objects.get(pk=instance.pk)
        super().update(instance, validated_data)
        if left_sibling is None:
            if parent is None:
                first_root = Organization.get_first_root_node()
                assert first_root is not None  # if there were no root, there would be no node and thus no `instance`
                instance.move(first_root, 'left')
            else:
                instance.move(parent, 'first-child')
        else:
            instance.move(left_sibling, 'right')
        # Reload because object is stale after move
        instance = instance._meta.model.objects.get(pk=instance.pk)
        return instance


class OrganizationSerializer(TreebeardModelSerializerMixin, serializers.ModelSerializer):
    uuid = serializers.UUIDField(required=False)

    class Meta:
        model = Organization
        list_serializer_class = BulkListSerializer
        fields = public_fields(Organization)

    def create(self, validated_data):
        instance = super().create(validated_data)
        # Add instance to active plan's related organizations
        request: WatchAdminRequest = self.context.get('request')
        plan = request.get_active_admin_plan()
        plan.related_organizations.add(instance)
        return instance


@register_view
class OrganizationViewSet(BulkModelViewSet):
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
            raise exceptions.NotFound(detail="Plan not found")
        return Organization.objects.available_for_plan(plan)


class PersonSerializer(
    BulkSerializerValidationInstanceMixin,
    serializers.ModelSerializer,
    ModelWithImageSerializerMixin,
):
    uuid = serializers.UUIDField(required=False)
    avatar_url = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.context.get('authorized_for_plan') is None:
            self.fields.pop('email')

    def get_avatar_url(self, obj: Person) -> str | None:
        return obj.get_avatar_url(self.context['request'])

    def validate_email(self, value):
        qs = Person.objects.filter(email__iexact=value)
        if self._instance is not None:
            qs = qs.exclude(pk=self._instance.pk)
        if qs.exists():
            raise serializers.ValidationError(_('Person with this email already exists'))
        return value

    def validate(self, data):
        for d in self.initial_data:
            if 'email' not in d:
                raise exceptions.ValidationError(_("Not all objects have an email address"))
        emails = Counter(data['email'] for data in self.initial_data)
        duplicates = [email for email, n in emails.most_common() if n > 1]
        if duplicates:
            # TODO: This should better be in validate_email to highlight the faulty table cells
            raise exceptions.ValidationError(_("Duplicate email addresses: %s") % ', '.join(duplicates))
        return data

    class Meta:
        model = Person
        list_serializer_class = BulkListSerializer
        fields = public_fields(Person, add_fields=['avatar_url'])


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

    def has_permission(self, request: AuthenticatedWatchRequest, view):
        perms = self.get_required_permissions(request.method, Person)
        plan = request.get_active_admin_plan()
        for perm in perms:
            if not self.check_permission(request.user, perm, plan=plan):
                return False
        return True

    def has_object_permission(self, request, view, obj):
        perms = self.get_required_object_permissions(request.method, Person)
        plan = request.get_active_admin_plan()
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        for perm in perms:
            if not self.check_permission(request.user, perm, person=obj, plan=plan):
                return False
        return True


@register_view
class PersonViewSet(ModelWithImageViewMixin, BulkModelViewSet):
    queryset = Person.objects.all()
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
            raise exceptions.NotFound(detail="Plan not found")

    def user_is_authorized_for_plan(self, plan):
        user = self.request.user
        return (
            user is not None
            and user.is_authenticated
            and hasattr(user, 'is_general_admin_for_plan')
            and user.is_general_admin_for_plan(plan)
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
        queryset = super().get_queryset()
        plan = self.get_plan()
        if plan is None:
            return queryset
        if not self.user_is_authorized_for_plan(plan):
            raise exceptions.PermissionDenied(detail="Not authorized")
        return queryset.available_for_plan(plan)


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
