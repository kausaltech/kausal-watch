from __future__ import annotations

import abc
import logging
import random
import re
import typing
from enum import Enum
from typing import (
    Any,
    Generic,
    Literal,
    Protocol,
    Self,
    TypedDict,
    cast,
)
from typing_extensions import TypeVar

from django import forms
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.postgres.fields import ArrayField
from django.core import checks
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import get_language, gettext_lazy as _
from modelcluster.forms import BaseChildFormSet
from modeltrans.translator import get_i18n_field
from modeltrans.utils import get_instance_field_value
from wagtail.fields import StreamField
from wagtail.models import Page, ReferenceIndex

import html2text
import humanize
import libvoikko  # type: ignore
import sentry_sdk
from tinycss2.color3 import parse_color

if typing.TYPE_CHECKING:
    from collections.abc import Iterable
    from datetime import datetime, timedelta

    from django.db.models import Model, QuerySet
    from django.http import HttpRequest
    from django.utils.choices import _Choices
    from modeltrans.fields import TranslationField
    from wagtail.blocks import StructBlock

    from aplans.types import UserOrAnon

    from actions.models.plan import Plan
    from users.models import User


logger = logging.getLogger(__name__)

try:
    libvoikko.VoikkoLibrary.open()
    voikko_fi = libvoikko.Voikko(language='fi')
    voikko_fi.setNoUglyHyphenation(True)
    voikko_fi.setMinHyphenatedWordLength(16)
except OSError:
    voikko_fi = None

_hyphenation_cache: dict[str, str] = {}


def hyphenate_fi(s):
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


def naturaltime(dt: datetime | timedelta) -> str:
    lang: str | None = get_language().split('-')[0]
    if lang == 'en':
        # Default locale
        lang = None

    try:
        # This should be fast
        humanize.activate(lang)  # type: ignore
    except FileNotFoundError as e:
        logger.warning(e)

    return humanize.naturaltime(dt)


def camelcase_to_underscore(name):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()


def underscore_to_camelcase(value: str) -> str:
    output = ""
    for word in value.split("_"):
        if not word:
            output += "_"
            continue
        output += word.capitalize()
    return output


class HasPublicFields(Protocol):
    public_fields: list[str]


def public_fields(
    model: HasPublicFields,
    add_fields: Iterable[str] | None = None,
    remove_fields: Iterable[str] | None = None,
) -> list[str]:
    fields = list(model.public_fields)
    if remove_fields is not None:
        fields = [f for f in fields if f not in remove_fields]
    if add_fields is not None:
        fields += add_fields
    return fields

# TODO: Remove this once the extensions are updated to use the register_view_helper from common
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
            regex = r'^[a-zA-Z0-9äöüåÄÖÜßÅ_.-]+$'
        super().__init__(regex, **kwargs)

class DateFormatOptions(models.TextChoices):
    FULL = 'FULL', _('Day, month and year (31.12.2020)')
    MONTH_YEAR = 'MONTH_YEAR', _('Month and year (12.2020)')
    YEAR = 'YEAR', _('Year (2020)')

class DateFormatField(models.CharField):
    def __init__(self, *args, **kwargs):
        kwargs['max_length'] = 16
        kwargs['choices'] = DateFormatOptions.choices
        super().__init__(*args, **kwargs)

_IDT = TypeVar('_IDT', bound=str | None, default=str)

class IdentifierField(models.CharField[_IDT, _IDT]):
    def __init__(self, *args, **kwargs):
        if 'validators' not in kwargs:
            kwargs['validators'] = [IdentifierValidator()]
        if 'max_length' not in kwargs:
            kwargs['max_length'] = 50
        if 'verbose_name' not in kwargs:
            kwargs['verbose_name'] = _('identifier')
        super().__init__(*args, **kwargs)


class OrderedModel(models.Model):
    """Like wagtailorderable.models.Orderable, but with additional functionality in filter_siblings()."""

    order: models.PositiveIntegerField[int, int] = models.PositiveIntegerField(default=0, editable=True, verbose_name=_('order'))
    sort_order_field = 'order'
    order_on_create: int | None

    class Meta:
        abstract = True

    def __init__(self, *args, order_on_create: int | None = None, **kwargs):
        """
        Create new model instance.

        Specify `order_on_create` to set the order to that value when saving if the instance is being created. If it is
        None, the order will instead be set to <maximum existing order> + 1.
        """
        super().__init__(*args, **kwargs)
        self.order_on_create = order_on_create

    def save(self, *args, **kwargs):
        if self.pk is None:
            order_on_create = getattr(self, 'order_on_create', None)
            if order_on_create is not None:
                self.order = order_on_create
            else:
                self.order = self.get_sort_order_max() + 1
        super().save(*args, **kwargs)

    @classmethod
    def check(cls, **kwargs) -> list[checks.CheckMessage]:
        errors = super().check(**kwargs)
        if getattr(cls.filter_siblings, '__isabstractmethod__', False):
            errors.append(checks.Warning("filter_siblings() not defined", hint="Implement filter_siblings() method", obj=cls))
        return errors

    # Probably for compatibility with things that expect a `sort_order` field as in wagtailorderable.models.Orderable
    @property
    def sort_order(self):
        return self.order

    @abc.abstractmethod
    def filter_siblings(self, qs: QuerySet[Self, Self]) -> QuerySet[Self, Self]:
        raise NotImplementedError("Implement in subclass")

    def get_sort_order_max(self) -> int:
        """
        Get the max sort_order when a new instance is created.

        If you order depends on a FK (eg. order of books for a specific author),
        you can override this method to filter on the FK.
        ```
        def get_sort_order_max(self):
            qs = self.__class__.objects.filter(author=self.author)
            return qs.aggregate(Max(self.sort_order_field))['sort_order__max'] or 0
        ```
        """
        mgr = cast('models.Manager', getattr(type(self), 'objects'))  # noqa: B009
        qs = mgr.all()
        if not getattr(self.filter_siblings, '__isabstractmethod__', False):
            qs = self.filter_siblings(qs)

        return qs.aggregate(models.Max(self.sort_order_field))['%s__max' % self.sort_order_field] or 0


class OrderedModelChildFormSet(BaseChildFormSet):
    """
    Fix ordering issues when using an `OrderedModel` in an `InlinePanel`.

    When using an `OrderedModel` in at `InlinePanel`, you will probably run into problems with the order field values
    being messed up by modelcluster's saving logic as it does not make sure that, e.g., the order of existing instances
    is updated when an element before them in the order is deleted or when a new element is inserted. This may lead to
    potential integrity constraint violations even if you override `OrderedModel.filter_siblings()` correctly.

    This class is intended to fix these issues by setting the order of *all* instances in the forms of the formset
    according to the form order and saving all instances.

    Define an edit handler for the modeladmin class containing the inline panel and override the `get_form_options()`
    method like this to make the formset use this class instead of `BaseChildFormSet`:

    ```
    def get_form_options(self):
        options = super().get_form_options()
        options['formsets']['<field_name>']['formset'] = OrderedModelChildFormSet
        return options
    ```
    """

    def save(self, commit=True):
        # `super().save()` may change the order field of instances in `self.ordered_forms` without persisting the new
        # values of the order field to the database unless something else changed in the respective instance.
        saved_instances = super().save(commit)
        if commit:
            for i, form in enumerate(self.ordered_forms):
                form.instance.order = i
                form.instance.save()
        return saved_instances


class PlanDefaultsModel:
    """
    Mixin for models that are plan-related.

    Model instances of this mixin have some plan-specific default values that
    must be set when creating new instances in the admin.
    """

    def initialize_plan_defaults(self, plan: Plan):
        raise NotImplementedError()


class PlanRelatedModel(PlanDefaultsModel, models.Model):
    wagtail_reference_index_ignore = False

    class Meta:
        abstract = True

    @classmethod
    def filter_by_plan(cls, plan: Plan, qs: QuerySet[Self, Self]) -> QuerySet[Self, Self]:
        return qs.filter(plan=plan)

    def get_plans(self) -> list[Plan]:
        return [cast('Plan', getattr(self, 'plan'))]  # noqa: B009

    def initialize_plan_defaults(self, plan: Plan):
        setattr(self, 'plan', plan)  # noqa: B010


class PlanRelatedOrderedModel(OrderedModel, PlanRelatedModel):
    class Meta:
        abstract = True

    def filter_siblings(self, qs: QuerySet[Self, Self]) -> QuerySet[Self, Self]:
        # Used by OrderedModel
        plans = self.get_plans()
        assert len(plans) == 1
        return self.filter_by_plan(plans[0], qs)


class RestrictedVisibilityModel(models.Model):
    class VisibilityState(models.TextChoices):
        INTERNAL = 'internal', _('Internal')
        PUBLIC = 'public', _('Public')

    visibility = models.CharField(
        blank=False, null=False,
        default=VisibilityState.PUBLIC,
        choices=VisibilityState.choices,
        max_length=20,
        verbose_name=_('visibility'),
    )

    class Meta:
        abstract = True

class InstancesEditableByMixin(models.Model):
    """
    Mixin for models such as CategoryType and AttributeType to restrict editing rights of categories/attributes.

    When you use this mixin, make sure in the validation of your model that `EditableBy.CONTACT_PERSONS` and
    `EditableBy.MODERATORS` are only accepted for `instances_editable_by` if your model instance can be associated with
    a specific action, and that this action is always supplied as the `action` to `is_instance_editable_by()`.

    If your model instance is not associated with a specific action, you may pass `action=None` to
    `is_instance_editable_by()`.

    For example, action attribute types and built-in field customizations are action-specific, whereas category types
    and category attribute types are not.
    """

    class EditableBy(models.TextChoices):
        AUTHENTICATED = 'authenticated', _('Authenticated users')  # practically you also need access to the edit page
        CONTACT_PERSONS = 'contact_persons', _('Contact persons')  # regardless of role; plan admins also can edit
        # It's not very meaningful to have EDITORS here because CONTACT_PERSONS can be used instead
        MODERATORS = 'moderators', _('Contact persons with moderator permissions')  # plan admins also can edit
        PLAN_ADMINS = 'plan_admins', _('Plan admins')
        NOT_EDITABLE = 'not_editable', _('Not editable')

    instances_editable_by = models.CharField(
        max_length=50,
        choices=EditableBy.choices,
        default=EditableBy.AUTHENTICATED,
        verbose_name=_('Edit rights'),
    )

    class Meta:
        abstract = True

    @property
    def instance_editability_is_action_specific(self):
        action_specific_values = [self.EditableBy.CONTACT_PERSONS, self.EditableBy.MODERATORS]
        return self.instances_editable_by in action_specific_values

    def is_instance_editable_by(self, user: UserOrAnon, plan: Plan, instance: Model | None):
        from actions.models.action import Action, ActionContactPerson
        # `action` may only be None if `self.instances_editable_by` is not action-specific
        if __debug__ and self.instance_editability_is_action_specific and instance is None:
            msg = (
                f"instances_editable_by has action-specific value '{self.instances_editable_by}', "
                                 "but no action has been supplied."
            )
            raise AssertionError(msg)

        if not user.is_authenticated:  # need to handle this case first, otherwise user does not have expected methods
            return False
        # Make linter happy; checking for User will fail because it may be a SimpleLazyObject
        assert not isinstance(user, AnonymousUser)
        if user.is_superuser:
            return True
        if self.instances_editable_by == self.EditableBy.NOT_EDITABLE:
            return False
        is_plan_admin = user.is_general_admin_for_plan(plan)
        if self.instances_editable_by == self.EditableBy.PLAN_ADMINS:
            return is_plan_admin
        if self.instances_editable_by == self.EditableBy.CONTACT_PERSONS:
            assert isinstance(instance, Action)
            is_contact_person = user.is_contact_person_for_action(instance)
            return is_contact_person or is_plan_admin
        if self.instances_editable_by == self.EditableBy.MODERATORS:
            assert isinstance(instance, Action)
            is_moderator = user.has_contact_person_role_for_action(ActionContactPerson.Role.MODERATOR, instance)
            return is_moderator or is_plan_admin
        if self.instances_editable_by == self.EditableBy.AUTHENTICATED:
            assert user.is_authenticated  # checked above
            return True

        msg = f"Unexpected value for instances_editable_by: {self.instances_editable_by}"
        raise Exception(msg)


class InstancesVisibleForMixin(models.Model):
    """
    Mixin for models such as AttributeType to restrict visibility of attributes.

    When you use this mixin, make sure in the validation of your model that `VisibleFor.CONTACT_PERSONS` and
    `VisibleFor.MODERATORS` are only accepted for `instances_visible_for` if your model instance can be associated with
    a specific action, and that this action is always supplied as the `action` to `is_instance_visible_for()`.

    If your model instance is not associated with a specific action, you may pass `action=None` to
    `is_instance_visible_for()`.

    For example, action attribute types and built-in field customizations are action-specific, whereas category types
    and category attribute types are not.
    """

    class VisibleFor(models.TextChoices):
        PUBLIC = 'public', _('Public')
        AUTHENTICATED = 'authenticated', _('Authenticated users')
        CONTACT_PERSONS = 'contact_persons', _('Contact persons')  # also visible for plan admins
        # It's not very meaningful to have EDITORS here because CONTACT_PERSONS can be used instead
        MODERATORS = 'moderators', _('Contact persons with "moderator" role')
        PLAN_ADMINS = 'plan_admins', _('Plan admins')

    instances_visible_for = models.CharField(
        max_length=50,
        choices=VisibleFor.choices,
        default=VisibleFor.PUBLIC,
        verbose_name=_('Visibility'),
    )

    class Meta:
        abstract = True

    @property
    def instance_visibility_is_action_specific(self):
        action_specific_values = [self.VisibleFor.CONTACT_PERSONS, self.VisibleFor.MODERATORS]
        return self.instances_visible_for in action_specific_values

    def is_instance_visible_for(self, user: UserOrAnon, plan: Plan, instance: Model | None) -> bool:
        from actions.models.action import Action, ActionContactPerson
        # `action` may only be None if `self.instances_visible_for` is not action-specific
        if __debug__ and self.instance_visibility_is_action_specific and instance is None:
            msg = (
                f"instances_visible_for has action-specific value '{self.instances_visible_for}', "
                                 "but no action has been supplied."
            )
            raise AssertionError(msg)

        if not user.is_authenticated:  # need to handle this case first, otherwise user does not have expected methods
            return self.instances_visible_for == self.VisibleFor.PUBLIC
        # Make linter happy; checking for User will fail because it may be a SimpleLazyObject
        assert not isinstance(user, AnonymousUser)
        if user.is_superuser:
            return True
        if not plan.is_visible_for_user(user):
            return False
        is_plan_admin = user.is_general_admin_for_plan(plan)
        if self.instances_visible_for == self.VisibleFor.PLAN_ADMINS:
            return is_plan_admin
        if self.instances_visible_for == self.VisibleFor.CONTACT_PERSONS:
            assert isinstance(instance, Action)
            is_contact_person = user.is_contact_person_for_action(instance)
            return is_contact_person or is_plan_admin
        if self.instances_visible_for == self.VisibleFor.MODERATORS:
            assert isinstance(instance, Action)
            is_moderator = user.has_contact_person_role_for_action(ActionContactPerson.Role.MODERATOR, instance)
            return is_moderator or is_plan_admin
        if self.instances_visible_for == self.VisibleFor.PUBLIC:
            return True
        if self.instances_visible_for == self.VisibleFor.AUTHENTICATED:
            assert user.is_authenticated  # checked above
            return True

        assert False, f"Unexpected value for instances_visible_for: {self.instances_visible_for}"  # noqa: B011, PT015


class ReferenceIndexedModelMixin:
    def delete(self, *args, **kwargs):
        """Remove referencing StreamField blocks before deleting."""

        references = ReferenceIndex.get_references_to(self)
        for ref in references:
            logger.debug(f"Removing referencing block '{ref.describe_source_field()}' from {ref.model_name} "
                         f"{ref.object_id}")
            model_class = ref.content_type.model_class()
            assert model_class is not None
            page = model_class.objects.get(id=ref.object_id)
            if isinstance(page, Page) and isinstance(ref.source_field, StreamField):
                stream_value = ref.source_field.value_from_object(page)
                model_field, block_id, block_field = ref.content_path.split('.')
                assert getattr(page, model_field) == stream_value
                block = next(iter(b for b in stream_value if b.id == block_id))
                assert block.value[block_field] == self
                stream_value.remove(block)
                page.save()
            else:
                message = (f"Unexpected type of reference ({type(page)} expected to be Page; {type(ref.source_field)} "
                           "expected to be StreamField)")
                logger.warning(message)
                sentry_sdk.capture_message(message)
        super().delete(*args, **kwargs)  # type: ignore


class ChoiceArrayField[ST](ArrayField[ST, ST]):  # pyright: ignore
    """
    A field that allows us to store an array of choices.

    Uses Django 1.9's postgres ArrayField
    and a MultipleChoiceField for its formfield.
    """

    def formfield(
        self,
        form_class: type[forms.Field] | None = None,
        choices_form_class: type[forms.ChoiceField] | None = None,
        choices: _Choices | None = None,
        **kwargs,
    ):
        form_class = form_class or forms.MultipleChoiceField
        choices = kwargs.pop('choices', self.base_field.choices)
        kwargs['choices_form_class'] = choices_form_class
        # Skip our parent's formfield implementation completely as we don't
        # care for it.
        return super(ArrayField, self).formfield(form_class=form_class, choices=choices, **kwargs)


def generate_identifier(qs, type_letter: str, field_name: str) -> str:
    # Try a couple of times to generate a unique identifier.
    for _i in range(10):
        rand = random.randint(0, 65535)  # noqa: S311
        identifier = '%s%04x' % (type_letter, rand)
        f = '%s__iexact' % field_name
        if qs.filter(**{f: identifier}).exists():
            continue
        return identifier
    raise Exception('Unable to generate an unused identifier')


def validate_css_color(s):
    if parse_color(s) is None:
        raise ValidationError(
            _('%(color)s is not a CSS color (e.g., "#112233", "red" or "rgb(0, 255, 127)")'),
            params={'color': s},
        )


class HasI18n(Protocol):
    i18n: TranslationField


class TranslatedModelMixin:
    def get_i18n_value(self: HasI18n, field_name: str, language: str | None = None, default_language: str | None = None):
        if language is None:
            language = get_language()
        key = '%s_%s' % (field_name, language)
        val = cast('dict', self.i18n).get(key)
        if val:
            return val
        return getattr(self, field_name)


type AdminSaveOperation = Literal['edit', 'create']

class AdminSaveContext(TypedDict):
    user: User
    operation: AdminSaveOperation


class ModificationTracking(models.Model):
    updated_at = models.DateTimeField(
        auto_now=True, editable=False, verbose_name=_('updated at'),
    )
    created_at = models.DateTimeField(
        auto_now_add=True, editable=False, verbose_name=_('created at'),
    )
    updated_by = models.ForeignKey(
        'users.User', blank=True, null=True, on_delete=models.SET_NULL,
        verbose_name=_('updated by'),
        related_name="%(app_label)s_updated_%(class)s",
    )
    created_by = models.ForeignKey(
        'users.User', blank=True, null=True, on_delete=models.SET_NULL,
        verbose_name=_('created by'),
        related_name="%(app_label)s_created_%(class)s",
    )

    class Meta:
        abstract = True

    def update_modification_metadata(self, user: User, operation: AdminSaveOperation):
        if operation == 'edit':
            self.updated_by = user
            self.save(update_fields=['updated_by'])
        elif operation == 'create':
            self.created_by = user
            self.save(update_fields=['created_by'])

    def handle_admin_save(self, context: AdminSaveContext):
        self.update_modification_metadata(context['user'], context['operation'])


def append_query_parameter(request: HttpRequest, url: str, parameter: str) -> str:
    value = request.GET.get(parameter)
    if value:
        assert '?' not in url
        return f'{url}?{parameter}={value}'
    return url


E = TypeVar('E', bound='MetadataEnum')
C = TypeVar('C')

class ConstantMetadata(Generic[E, C]):
    identifier: E
    color: str | None

    def with_identifier(self, identifier: E):
        self.identifier = identifier
        return self

    def with_context(self, context: C):
        return self


CM = TypeVar('CM', bound=ConstantMetadata[Any, Any])

class MetadataEnum(Enum):
    value: ConstantMetadata[Any, Any]

    def get_data(self, context=None):
        return self.value.with_identifier(self).with_context(context)


def get_available_variants_for_language(language: str):
    if len(language) != 2:
        return language
    return [lang_code for lang_code, _ in settings.LANGUAGES if lang_code[0:2] == language]


def convert_html_to_text(html):
    # Create an instance of the HTML2Text converter
    if html is None:
        return ''
    converter = html2text.HTML2Text()

    # Configure the converter settings
    converter.body_width = 0  # Disable text wrapping
    converter.single_line_break = True  # Convert single line breaks to newlines
    converter.ul_item_mark = '-'  # Set the unordered list item marker

    # Convert the HTML content to plain text
    text = converter.handle(html)
    text = re.sub(r'\n{3,}', '\n', text)
    # html2text escapes markdown formatting
    # which can't be turned off!
    text = re.sub(r'\\-', '-', text)
    return text

LANGUAGE_COLLATORS = {
    'da': 'da-x-icu',
    'de': 'de-x-icu',
    'de-CH': 'de-CH-x-icu',
    'en': 'en-US-x-icu',
    'en-AU': 'en-AU-x-icu',
    'en-GB': 'en-GB-x-icu',
    'es': 'es-x-icu',
    'es-US': 'es-US-x-icu',
    'fi': 'fi-FI-x-icu',
    'lv': 'lv-LV-x-icu',
    'sv': 'sv-SE-x-icu',
    'sv-FI': 'sv-FI-x-icu',
    'pt': 'pt-x-icu',
    'pt-BR': 'pt-BR-x-icu',
}

def get_collator(lang: str) -> str:
    return LANGUAGE_COLLATORS.get(lang, 'en-US-x-icu')


if typing.TYPE_CHECKING:
    _StructBlock = StructBlock
else:
    _StructBlock = object

class StaticBlockToStructBlockWorkaroundMixin(_StructBlock):
    # Workaround for migration from StaticBlock to StructBlock
    def bulk_to_python(self, values):
        li = list(values)
        if len(li) == 1 and li[0] is None:
            values = [{}]
        return super().bulk_to_python(values)
