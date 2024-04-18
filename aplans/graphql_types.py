from __future__ import annotations

import functools
import uuid

import typing
from typing import Any, ClassVar, Protocol, Sequence, Type, TypeVar, Generic
import graphene
from enum import Enum
import re

from django.db.models import Model, QuerySet
from django.db.models.constants import LOOKUP_SEP
from django.utils.translation import gettext_lazy as _
from graphql import GraphQLResolveInfo
from graphql.language.ast import OperationDefinitionNode
import graphene_django_optimizer as gql_optimizer
from graphene.utils.str_converters import to_camel_case, to_snake_case
from graphene.utils.trim_docstring import trim_docstring
from graphene_django import DjangoObjectType
from grapple.registry import registry as grapple_registry
from modeltrans.translator import get_i18n_field

from actions.models.plan import Plan
from aplans.types import WatchAPIRequest
from aplans.utils import get_language_from_default_language_field
from users.models import User


graphene_registry: list[Type[graphene.ObjectType | graphene.Interface]] = []


def get_i18n_field_with_fallback(field_name: str, obj: Model, info: GQLInfo):
    i18n_field = get_i18n_field(obj._meta.model)
    fallback_value = getattr(obj, field_name)
    fallback_lang = get_language_from_default_language_field(obj, i18n_field)
    fallback = (fallback_value, fallback_lang)

    active_language = getattr(info.context, '_graphql_query_language', None)
    if not active_language:
        return fallback

    active_language = active_language.lower().replace('-', '_')

    i18n_values = getattr(obj, i18n_field.name)
    if i18n_values is None or active_language == fallback_lang:
        return fallback

    lang_field_name = '%s_%s' % (field_name, active_language)
    trans_value = i18n_values.get(lang_field_name)
    if not trans_value:
        return fallback

    trans_value = i18n_values.get(lang_field_name, getattr(obj, field_name))
    return trans_value, active_language


def resolve_i18n_field(field_name, obj, info):
    value, lang = get_i18n_field_with_fallback(field_name, obj, info)
    return value


M = TypeVar('M', bound=Model)

class DjangoNode(DjangoObjectType, Generic[M]):
    @staticmethod
    def resolve_id(root, info):
        return getattr(root, 'pk', None) or f'unpublished-{uuid.uuid4()}'

    @classmethod
    def __init_subclass_with_meta__(cls, **kwargs: Any):
        if 'name' not in kwargs:
            # Remove the trailing 'Node' from the object types
            kwargs['name'] = re.sub(r'Node$', '', cls.__name__)

        model: Type[M] = kwargs['model']
        assert model.__doc__ is not None
        is_autogen = re.match(r'^\w+\([\w_, ]+\)$', model.__doc__)
        if 'description' not in kwargs and not cls.__doc__ and not is_autogen:
            kwargs['description'] = trim_docstring(model.__doc__)

        super().__init_subclass_with_meta__(**kwargs)

        # Set default resolvers for i18n fields
        i18n_field = get_i18n_field(cls._meta.model)
        if i18n_field is not None:
            fields = cls._meta.fields
            for translated_field_name in i18n_field.fields:
                # translated_field_name is only in fields if it is in *Node.Meta.fields
                field = fields.get(translated_field_name)
                if field is not None and field.resolver is None and not hasattr(cls, 'resolve_%s' % translated_field_name):
                    resolver = functools.partial(resolve_i18n_field, translated_field_name)
                    only = [translated_field_name, i18n_field.name]
                    select_related=[]
                    default_language_field = i18n_field.default_language_field
                    if default_language_field:
                        parsed_default_language_field = default_language_field.split(LOOKUP_SEP)
                        only.append(default_language_field)
                        if len(parsed_default_language_field) > 1:
                            related_path = parsed_default_language_field[:-1]
                            select_related.append(LOOKUP_SEP.join(related_path))
                    hints = dict(
                        only=only,
                        select_related=select_related
                    )
                    apply_hints = gql_optimizer.resolver_hints(**hints)
                    field.resolver = apply_hints(resolver)

    class Meta:
        abstract = True


def set_active_plan(info, plan):
    info.context._graphql_active_plan = plan


@typing.overload
def get_plan_from_context(info: GQLInfo, plan_identifier: None = None) -> Plan: ...


@typing.overload
def get_plan_from_context(info: GQLInfo, plan_identifier: str) -> Plan | None: ...


def get_plan_from_context(info: GQLInfo, plan_identifier: str | None = None) -> Plan | None:
    if plan_identifier is None:
        plan = getattr(info.context, '_graphql_active_plan', None)
        if not plan:
            raise Exception('No plan in context')
        return plan

    cache = getattr(info.context, '_plan_cache', None)
    if cache is None:
        cache = info.context._plan_cache = {}  # type: ignore

    if plan_identifier in cache:
        return cache[plan_identifier]
    plan = Plan.objects.filter(identifier=plan_identifier).first()
    cache[plan_identifier] = plan
    set_active_plan(info, plan)
    return plan


class SupportsOrderable(Protocol):
    ORDERABLE_FIELDS: ClassVar[Sequence[str]]


Q = TypeVar('Q', bound=QuerySet)

def order_queryset(qs: Q, node_class: Type[SupportsOrderable], order_by: str | None) -> Q:
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
            [to_camel_case(x) for x in orderable_fields]
        ))
    assert order_by is not None
    qs = qs.order_by(desc + order_by)
    return qs


OT = TypeVar('OT', bound=graphene.ObjectType)

def register_graphene_node(cls: Type[OT]) -> Type[OT]:
    global graphene_registry
    graphene_registry.append(cls)
    return cls


IT = TypeVar('IT', bound=graphene.Interface)


def register_graphene_interface(cls: Type[IT]) -> Type[IT]:
    global graphene_registry
    graphene_registry.append(cls)
    return cls


def register_django_node(cls: Type[M]) -> Type[M]:
    model = cls._meta.model
    grapple_registry.django_models[model] = cls
    return cls


def replace_image_node(cls):
    model = cls._meta.model
    grapple_registry.images[model] = cls
    return cls


class AuthenticatedUserNode(graphene.ObjectType):
    pass


class GQLInfo(GraphQLResolveInfo):
    context: WatchAPIRequest
    operation: OperationDefinitionNode


class AdminButton(graphene.ObjectType):
    url = graphene.String(required=True)
    label = graphene.String(required=True)
    classname = graphene.String(required=True)
    title = graphene.String(required=False)
    target = graphene.String(required=False)


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


WorkflowStateGrapheneEnum = graphene.Enum.from_enum(WorkflowStateEnum, name='WorkflowState')  # type: ignore


class WorkflowStateDescription(graphene.ObjectType):
    id = graphene.String()
    description = graphene.String()
