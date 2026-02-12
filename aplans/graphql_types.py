from __future__ import annotations

import typing
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar, Protocol

import graphene
import strawberry as sb
from django.db.models import Model, QuerySet
from django.utils.translation import gettext_lazy as _
from graphene.utils.str_converters import to_camel_case, to_snake_case

from grapple.registry import registry as grapple_registry

from kausal_common.graphene import DjangoNode as BaseDjangoNode

if typing.TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import type_check_only

    from kausal_common.graphene import GQLInfo as CommonGQLInfo

    from aplans.schema_context import WatchGraphQLContext

    from actions.models.plan import Plan
    from users.models import User


class DjangoNode[M: Model](BaseDjangoNode[M]):
    class Meta:
        abstract = True

    @staticmethod
    def resolve_id(root, info) -> str:
        return getattr(root, 'pk', None) or f'unpublished-{uuid.uuid4()}'


def set_active_plan(info: GQLInfo, plan: Plan):
    info.context.active_plan = plan
    assert plan.is_visible_for_user(info.context.user), 'Plan is not visible for user'


def is_plan_context_active(info: GQLInfo) -> bool:
    return info.context.active_plan is not None


@typing.overload
def get_plan_from_context(info: GQLInfo, plan_identifier: None = None) -> Plan: ...


@typing.overload
def get_plan_from_context(info: GQLInfo, plan_identifier: str) -> Plan | None: ...


def get_plan_from_context(info: GQLInfo, plan_identifier: str | None = None) -> Plan | None:
    if plan_identifier is None:
        plan = info.context.active_plan
        if not plan:
            raise Exception('No plan in context')
        assert plan.is_visible_for_user(info.context.user), 'Plan is not visible for user'
        return plan

    plan_cache = info.context.cache.for_plan_identifier(plan_identifier=plan_identifier)
    plan = plan_cache.plan
    if not plan.is_visible_for_user(info.context.user):
        return None
    set_active_plan(info, plan)
    return plan


class SupportsOrderable(Protocol):
    ORDERABLE_FIELDS: ClassVar[Sequence[str]]


def order_queryset[QS: QuerySet[Any]](qs: QS, node_class: type[SupportsOrderable], order_by: str | None) -> QS:
    if order_by is None:
        return qs

    orderable_fields = node_class.ORDERABLE_FIELDS
    if order_by[0] == '-':
        desc = '-'
        order_by = order_by[1:]
    else:
        desc = ''
    order_by = to_snake_case(order_by)
    if order_by not in orderable_fields:
        raise ValueError('Only orderable fields are: %s' % ', '.join(
            [to_camel_case(x) for x in orderable_fields],
        ))
    assert order_by is not None
    qs = qs.order_by(desc + order_by)
    return qs


def register_django_node[DN: DjangoNode[Any]](cls: type[DN]) -> type[DN]:
    meta = cls._meta
    model = meta.model
    assert model not in grapple_registry.django_models, f"Model {model} already registered"
    grapple_registry.django_models[model] = cls
    return cls


def replace_image_node(cls):
    model = cls._meta.model
    grapple_registry.images[model] = cls
    return cls


class AdminButton(graphene.ObjectType[Any]):
    url = graphene.String(required=True)
    label = graphene.String(required=True)
    classname = graphene.String(required=True)
    title = graphene.String(required=False)
    target = graphene.String(required=False)
    icon = graphene.String(required=False)


@sb.enum(name='WorkflowState')
class WorkflowStateEnum(Enum):
    PUBLISHED = 'PUBLISHED'
    APPROVED = 'APPROVED'
    DRAFT = 'DRAFT'

    def is_visible_to_user(self, user: User, plan: Plan):
        if self == WorkflowStateEnum.PUBLISHED:
            return True
        if not user.is_authenticated:
            return False
        if self == WorkflowStateEnum.APPROVED:
            return True
        if self == WorkflowStateEnum.DRAFT:
            return user.can_access_admin(plan)
        return False

    @property
    def description(self):
        if self == WorkflowStateEnum.PUBLISHED:
            return _('Published')
        if self == WorkflowStateEnum.APPROVED:
            return _('Approved')
        if self == WorkflowStateEnum.DRAFT:
            return _('Draft')
        return None


WorkflowStateGrapheneEnum = graphene.Enum.from_enum(WorkflowStateEnum, name='WorkflowState')  # type: ignore  # pyright: ignore[reportCallIssue]


class WorkflowStateDescription(graphene.ObjectType[Any]):
    id = graphene.String(required=True)
    description = graphene.String(required=False)


if TYPE_CHECKING:
    @type_check_only
    class GQLInfo(CommonGQLInfo):  # pyright: ignore
        context: WatchGraphQLContext  # type: ignore[assignment]


type SBInfo = sb.Info['WatchGraphQLContext']
