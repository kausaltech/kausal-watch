import random
import re
from typing import Iterable, List, Type

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import get_language, gettext_lazy as _

import libvoikko
import pytz
from tinycss2.color3 import parse_color


LOCAL_TZ = pytz.timezone('Europe/Helsinki')

try:
    voikko_fi = libvoikko.Voikko(language='fi')
    voikko_fi.setNoUglyHyphenation(True)
    voikko_fi.setMinHyphenatedWordLength(16)
except OSError:
    voikko_fi = None

_hyphenation_cache = {}


def hyphenate(s):
    if voikko_fi is None:
        return s

    tokens = voikko_fi.tokens(s)
    out = ''
    for t in tokens:
        if t.tokenTypeName != 'WORD':
            out += t.tokenText
            continue

        cached = _hyphenation_cache.get(t.tokenText, None)
        if cached is not None:
            out += cached
        else:
            val = voikko_fi.hyphenate(t.tokenText, separator='\u00ad')
            _hyphenation_cache[t.tokenText] = val
            out += val
    return out


def camelcase_to_underscore(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def public_fields(
    model: Type[models.Model],
    add_fields: Iterable[str] = None,
    remove_fields: Iterable[str] = None
) -> List[str]:
    fields = model.public_fields
    if remove_fields is not None:
        fields = [f for f in fields if f not in remove_fields]
    if add_fields is not None:
        fields += add_fields
    return fields


def register_view_helper(view_list, klass, name=None, basename=None):
    if not name:
        if klass.serializer_class:
            model = klass.serializer_class.Meta.model
        else:
            model = klass.queryset.model
        name = camelcase_to_underscore(model._meta.object_name)

    entry = {'class': klass, 'name': name}
    if basename is not None:
        entry['basename'] = basename

    view_list.append(entry)

    return klass


class IdentifierValidator(RegexValidator):
    def __init__(self, regex=None, **kwargs):
        if regex is None:
            regex = r'^[a-zA-Z0-9_.-]+$'
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


class OrderedModel(models.Model):
    order = models.PositiveIntegerField(default=0, editable=True, verbose_name=_('order'))
    sort_order_field = 'order'

    def __init__(self, *args, order_on_create=None, **kwargs):
        """
        Specify `order_on_create` to set the order to that value when saving if the instance is being created. If it is
        None, the order will instead be set to <maximum existing order> + 1.
        """
        super().__init__(*args, **kwargs)
        self.order_on_create = order_on_create

    @property
    def sort_order(self):
        return self.order

    def get_sort_order_max(self):
        """
        Method used to get the max sort_order when a new instance is created.
        If you order depends on a FK (eg. order of books for a specific author),
        you can override this method to filter on the FK.
        ```
        def get_sort_order_max(self):
            qs = self.__class__.objects.filter(author=self.author)
            return qs.aggregate(Max(self.sort_order_field))['sort_order__max'] or 0
        ```
        """
        qs = self.__class__.objects.all()
        if hasattr(self, 'filter_siblings'):
            qs = self.filter_siblings(qs)

        return qs.aggregate(models.Max(self.sort_order_field))['%s__max' % self.sort_order_field] or 0

    def save(self, *args, **kwargs):
        if self.pk is None:
            if getattr(self, 'order_on_create', None) is not None:
                self.order = self.order_on_create
            else:
                self.order = self.get_sort_order_max() + 1
        super().save(*args, **kwargs)

    class Meta:
        abstract = True


class PlanDefaultsModel:
    '''Model instances of this mixin have
    some plan-specific default values that
    must be set when creating new instances
    in the admin.
    '''
    def initialize_plan_defaults(self, plan):
        raise NotImplementedError()


class PlanRelatedModel(PlanDefaultsModel):
    @classmethod
    def filter_by_plan(cls, plan, qs):
        return qs.filter(plan=plan)

    def get_plans(self):
        return [self.plan]

    def initialize_plan_defaults(self, plan):
        self.plan = plan

    def filter_siblings(self, qs):
        plans = self.get_plans()
        assert len(plans) == 1
        return self.filter_by_plan(plans[0], qs)


class ChoiceArrayField(ArrayField):
    """
    A field that allows us to store an array of choices.

    Uses Django 1.9's postgres ArrayField
    and a MultipleChoiceField for its formfield.
    """

    def formfield(self, **kwargs):
        defaults = {
            'form_class': forms.MultipleChoiceField,
            'choices': self.base_field.choices,
        }
        defaults.update(kwargs)
        # Skip our parent's formfield implementation completely as we don't
        # care for it.
        # pylint:disable=bad-super-call
        return super(ArrayField, self).formfield(**defaults)


def generate_identifier(qs, type_letter: str, field_name: str) -> str:
    # Try a couple of times to generate a unique identifier.
    for i in range(0, 10):
        rand = random.randint(0, 65535)
        identifier = '%s%04x' % (type_letter, rand)
        f = '%s__iexact' % field_name
        if qs.filter(**{f: identifier}).exists():
            continue
        return identifier
    else:
        raise Exception('Unable to generate an unused identifier')


def validate_css_color(s):
    if parse_color(s) is None:
        raise ValidationError(
            _('%(color)s is not a CSS color (e.g., "#112233", "red" or "rgb(0, 255, 127)")'),
            params={'color': s},
        )


class TranslatedModelMixin:
    def get_i18n_value(self, field_name: str, language: str = None, default_language: str = None):
        if language is None:
            language = get_language()
        key = '%s_%s' % (field_name, language)
        val = self.i18n.get(key)
        if val:
            return val
        return getattr(self, field_name)


def get_supported_languages():
    for x in settings.LANGUAGES:
        yield x


def get_default_language():
    return settings.LANGUAGES[0][0]


User = get_user_model()


class ModificationTracking(models.Model):
    updated_at = models.DateTimeField(
        auto_now=True, editable=False, verbose_name=_('updated at')
    )
    created_at = models.DateTimeField(
        auto_now_add=True, editable=False, verbose_name=_('created at')
    )
    updated_by = models.ForeignKey(
        User, blank=True, null=True, on_delete=models.SET_NULL,
        verbose_name=_('updated by'),
        related_name="%(app_label)s_updated_%(class)s",
    )
    created_by = models.ForeignKey(
        User, blank=True, null=True, on_delete=models.SET_NULL,
        verbose_name=_('created by'),
        related_name="%(app_label)s_created_%(class)s",
    )

    class Meta:
        abstract = True

    def update_modification_metadata(self, user, operation):
        if operation == 'edit':
            self.updated_by = user
            self.save(update_fields=['updated_by'])
        elif operation == 'create':
            self.created_by = user
            self.save(update_fields=['created_by'])

    def handle_admin_save(self, context=None):
        self.update_modification_metadata(context.get('user'), context.get('operation'))
