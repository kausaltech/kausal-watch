from __future__ import annotations

import functools
import typing
import graphene
import re

from graphql import GraphQLResolveInfo
from graphql.language.ast import OperationDefinitionNode
import graphene_django_optimizer as gql_optimizer
from graphene.utils.str_converters import to_camel_case, to_snake_case
from graphene.utils.trim_docstring import trim_docstring
from graphene_django import DjangoObjectType
from grapple.registry import registry as grapple_registry
from modeltrans.translator import get_i18n_field

from actions.models import Plan
from aplans.types import WatchAPIRequest


graphene_registry = []


def get_i18n_field_with_fallback(field_name, obj, info):
    fallback_value = getattr(obj, field_name)
    fallback_lang = 'fi'  # FIXME

    fallback = (fallback_value, fallback_lang)

    active_language = getattr(info.context, '_graphql_query_language', None)
    if not active_language:
        return fallback

    active_language = active_language.lower().replace('-', '_')

    i18n_field = get_i18n_field(obj._meta.model)

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


class DjangoNode(DjangoObjectType):
    @classmethod
    def __init_subclass_with_meta__(cls, **kwargs):
        if 'name' not in kwargs:
            # Remove the trailing 'Node' from the object types
            kwargs['name'] = re.sub(r'Node$', '', cls.__name__)

        model = kwargs['model']
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
                    apply_hints = gql_optimizer.resolver_hints(only=[translated_field_name, i18n_field.name])
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


def order_queryset(qs, node_class, order_by):
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
    qs = qs.order_by(desc + order_by)
    return qs


def register_graphene_node(cls):
    global graphene_registry
    graphene_registry.append(cls)
    return cls


def register_django_node(cls):
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
