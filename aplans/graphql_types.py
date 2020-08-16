import re
import functools
from graphene_django import DjangoObjectType
import graphene_django_optimizer as gql_optimizer
from modeltrans.translator import get_i18n_field


def get_i18n_field_with_fallback(field_name, obj, info):
    fallback_value = getattr(obj, field_name)
    fallback_lang = 'fi'  # FIXME

    fallback = (fallback_value, fallback_lang)

    active_language = getattr(info.context, '_graphql_query_language', None)
    if not active_language:
        return fallback

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
        super().__init_subclass_with_meta__(**kwargs)

        # Set default resolvers for i18n fields
        i18n_field = get_i18n_field(cls._meta.model)
        if i18n_field is not None:
            fields = cls._meta.fields
            for translated_field_name in i18n_field.fields:
                field = fields[translated_field_name]
                if field.resolver is None and not hasattr(cls, 'resolve_%s' % translated_field_name):
                    resolver = functools.partial(resolve_i18n_field, translated_field_name)
                    apply_hints = gql_optimizer.resolver_hints(only=[translated_field_name, i18n_field.name])
                    field.resolver = apply_hints(resolver)

    class Meta:
        abstract = True
