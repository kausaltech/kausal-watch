import re
from django.db import models
from django.core.validators import RegexValidator
from django.utils.translation import gettext_lazy as _


def camelcase_to_underscore(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def register_view_helper(view_list, klass, name=None, base_name=None):
    if not name:
        model = klass.serializer_class.Meta.model
        name = camelcase_to_underscore(model._meta.object_name)

    entry = {'class': klass, 'name': name}
    if base_name is not None:
        entry['base_name'] = base_name

    view_list.append(entry)

    return klass


class IdentifierValidator(RegexValidator):
    def __init__(self, regex=None, **kwargs):
        if regex is not None:
            regex = r'^[a-z0-9_]+$'
        super().__init__(regex, **kwargs)


class IdentifierField(models.CharField):
    def __init__(self, *args, **kwargs):
        if 'validators' not in kwargs:
            kwargs['validators'] = [IdentifierValidator()]
        if 'max_length' not in kwargs:
            kwargs['max_length'] = 50
        if 'verbose_name' not in kwargs:
            kwargs['verbose_name'] = _('identifier')
        super().__init__(*args, **kwargs)
