from __future__ import annotations
import abc
from django.contrib.auth.models import AnonymousUser

import humanize
import libvoikko  # type: ignore
import logging
import random
import re
from typing import Generic, Iterable, List, Protocol, Self, Sequence, TYPE_CHECKING, TypeVar

import sentry_sdk
from datetime import datetime, timedelta
from django import forms
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core import checks
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils.translation import get_language, gettext_lazy as _
from enum import Enum
from tinycss2.color3 import parse_color  # type: ignore
from wagtail.fields import StreamField
from wagtail.models import Page, ReferenceIndex

from aplans.types import UserOrAnon

if TYPE_CHECKING:
    from actions.models.action import Action, Plan
    from actions.models.plan import Plan


logger = logging.getLogger(__name__)

try:
    voikko_fi = libvoikko.Voikko(language='fi')
    voikko_fi.setNoUglyHyphenation(True)
    voikko_fi.setMinHyphenatedWordLength(16)
except OSError:
    voikko_fi = None

_hyphenation_cache: dict[str, str] = {}


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
    public_fields: Sequence[str]


def public_fields(
    model: HasPublicFields,
    add_fields: Iterable[str] | None = None,
    remove_fields: Iterable[str] | None = None
) -> List[str]:
    fields = list(model.public_fields)
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
            regex = r'^[a-zA-Z0-9äöüåÄÖÜßÅ_.-]+$'
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
    order_on_create: int | None

    def __init__(self, *args, order_on_create: int | None = None, **kwargs):
        """
        Specify `order_on_create` to set the order to that value when saving if the instance is being created. If it is
        None, the order will instead be set to <maximum existing order> + 1.
        """
        super().__init__(*args, **kwargs)
        self.order_on_create = order_on_create

    @classmethod
    def check(cls, **kwargs):
        errors = super().check(**kwargs)
        if getattr(cls.filter_siblings, '__isabstractmethod__', False):
            errors.append(checks.Warning("filter_siblings() not defined", hint="Implement filter_siblings() method", obj=cls))
        return errors

    @property
    def sort_order(self):
        return self.order

    @abc.abstractmethod
    def filter_siblings(self, qs: models.QuerySet[Self]) -> models.QuerySet[Self]:
        raise NotImplementedError("Implement in subclass")

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
        qs = self.__class__.objects.all()  # type: ignore
        if not getattr(self.filter_siblings, '__isabstractmethod__', False):
            qs = self.filter_siblings(qs)

        return qs.aggregate(models.Max(self.sort_order_field))['%s__max' % self.sort_order_field] or 0

    def save(self, *args, **kwargs):
        if self.pk is None:
            order_on_create = getattr(self, 'order_on_create', None)
            if order_on_create is not None:
                self.order = order_on_create
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
    def initialize_plan_defaults(self, plan: Plan):
        raise NotImplementedError()

M = TypeVar('M', bound=models.Model)


class PlanRelatedModel(PlanDefaultsModel, Generic[M]):
    wagtail_reference_index_ignore = False

    @classmethod
    def filter_by_plan(cls, plan: Plan, qs: models.QuerySet[M]) -> models.QuerySet[M]:
        return qs.filter(plan=plan)

    def get_plans(self):
        return [self.plan]  # type: ignore[attr-defined]

    def initialize_plan_defaults(self, plan: Plan):
        # Using setattr() here to avoid type pollution in subclasses
        setattr(self, 'plan', plan)

    def filter_siblings(self, qs: models.QuerySet[M]) -> models.QuerySet[M]:
        # Used by OrderedModel
        plans = self.get_plans()
        assert len(plans) == 1
        return self.filter_by_plan(plans[0], qs)


class InstancesEditableByMixin(models.Model):
    """Mixin for models such as CategoryType and AttributeType to restrict editing rights of categories/attributes.

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

    @property
    def instance_editability_is_action_specific(self):
        ACTION_SPECIFIC_VALUES = [self.EditableBy.CONTACT_PERSONS, self.EditableBy.MODERATORS]
        return self.instances_editable_by in ACTION_SPECIFIC_VALUES

    def is_instance_editable_by(self, user: UserOrAnon, plan: Plan, action: Action | None):
        from actions.models.action import Action, ActionContactPerson
        # `action` may only be None if `self.instances_editable_by` is not action-specific
        if __debug__:
            if self.instance_editability_is_action_specific and action is None:
                raise AssertionError(f"instances_editable_by has action-specific value '{self.instances_editable_by}', "
                                     "but no action has been supplied.")

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
            assert isinstance(action, Action)
            is_contact_person = user.is_contact_person_for_action(action)
            return is_contact_person or is_plan_admin
        if self.instances_editable_by == self.EditableBy.MODERATORS:
            assert isinstance(action, Action)
            is_moderator = user.has_contact_person_role_for_action(ActionContactPerson.Role.MODERATOR, action)
            return is_moderator or is_plan_admin
        if self.instances_editable_by == self.EditableBy.AUTHENTICATED:
            assert user.is_authenticated  # checked above
            return True
        assert False, f"Unexpected value for instances_editable_by: {self.instances_editable_by}"

    class Meta:
        abstract = True


class InstancesVisibleForMixin(models.Model):
    """Mixin for models such as AttributeType to restrict visibility of attributes.

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

    @property
    def instance_visibility_is_action_specific(self):
        ACTION_SPECIFIC_VALUES = [self.VisibleFor.CONTACT_PERSONS, self.VisibleFor.MODERATORS]
        return self.instances_visible_for in ACTION_SPECIFIC_VALUES

    @classmethod
    def get_visibility_permissions_for_user(cls, user: UserOrAnon, plan: Plan | None) -> set[VisibleFor]:
        # FIXME: Use the method above here instead for consistency
        if hasattr(user, '_instance_visibility_perms'):
            return user._instance_visibility_perms
        permissions = [InstancesVisibleForMixin.VisibleFor.PUBLIC]
        if not user.is_authenticated:
            return set(permissions)

        permissions.append(InstancesVisibleForMixin.VisibleFor.AUTHENTICATED)
        is_plan_admin = plan is not None and user.is_general_admin_for_plan(plan)
        if is_plan_admin:
            permissions.append(InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS)
        # FIXME: Check if the user is a contact person for the object, not for *anything* in the plan.
        is_contact_person = plan is not None and user.is_contact_person_in_plan(plan)
        if is_contact_person or is_plan_admin:
            permissions.append(InstancesVisibleForMixin.VisibleFor.CONTACT_PERSONS)
        user._instance_visibility_perms = set(permissions)
        return user._instance_visibility_perms

    def is_instance_visible_for(self, user: UserOrAnon, plan: Plan, action: Action | None):
        from actions.models.action import Action, ActionContactPerson
        # `action` may only be None if `self.instances_visible_for` is not action-specific
        if __debug__:
            if self.instance_visibility_is_action_specific and action is None:
                raise AssertionError(f"instances_visible_for has action-specific value '{self.instances_visible_for}', "
                                     "but no action has been supplied.")

        if not user.is_authenticated:  # need to handle this case first, otherwise user does not have expected methods
            return self.instances_visible_for == self.VisibleFor.PUBLIC
        # Make linter happy; checking for User will fail because it may be a SimpleLazyObject
        assert not isinstance(user, AnonymousUser)
        if user.is_superuser:
            return True
        is_plan_admin = user.is_general_admin_for_plan(plan)
        if self.instances_visible_for == self.VisibleFor.PLAN_ADMINS:
            return is_plan_admin
        if self.instances_visible_for == self.VisibleFor.CONTACT_PERSONS:
            assert isinstance(action, Action)
            is_contact_person = user.is_contact_person_for_action(action)
            return is_contact_person or is_plan_admin
        if self.instances_visible_for == self.VisibleFor.MODERATORS:
            assert isinstance(action, Action)
            is_moderator = user.has_contact_person_role_for_action(ActionContactPerson.Role.MODERATOR, action)
            return is_moderator or is_plan_admin
        if self.instances_visible_for == self.VisibleFor.PUBLIC:
            return True
        if self.instances_visible_for == self.VisibleFor.AUTHENTICATED:
            assert user.is_authenticated  # checked above
            return True
        assert False, f"Unexpected value for instances_visible_for: {self.instances_visible_for}"

    class Meta:
        abstract = True


class ReferenceIndexedModelMixin:
    def delete(self, *args, **kwargs):
        """Remove referencing StreamField blocks before deleting."""

        references = ReferenceIndex.get_references_to(self)
        for ref in references:
            logger.debug(f"Removing referencing block '{ref.describe_source_field()}' from {ref.model_name} "
                         f"{ref.object_id}")
            page = ref.content_type.model_class().objects.get(id=ref.object_id)
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


class HasI18n(Protocol):
    i18n: dict


class TranslatedModelMixin:
    def get_i18n_value(self: HasI18n, field_name: str, language: str | None = None, default_language: str | None = None):
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


class ModificationTracking(models.Model):
    updated_at = models.DateTimeField(
        auto_now=True, editable=False, verbose_name=_('updated at')
    )
    created_at = models.DateTimeField(
        auto_now_add=True, editable=False, verbose_name=_('created at')
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

    def update_modification_metadata(self, user, operation):
        if operation == 'edit':
            self.updated_by = user
            self.save(update_fields=['updated_by'])
        elif operation == 'create':
            self.created_by = user
            self.save(update_fields=['created_by'])

    def handle_admin_save(self, context=None):
        self.update_modification_metadata(context.get('user'), context.get('operation'))


def append_query_parameter(request, url, parameter):
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


CM = TypeVar('CM', bound=ConstantMetadata)


class MetadataEnum(Enum):
    value: 'ConstantMetadata'

    def get_data(self, context=None):
        return self.value.with_identifier(self).with_context(context)


def get_available_variants_for_language(language: str):
    if len(language) != 2:
        return language
    return [lang_code for lang_code, _ in settings.LANGUAGES if lang_code[0:2] == language]
