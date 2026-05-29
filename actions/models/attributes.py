from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar, Literal, Self, cast, override

import reversion
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import ObjectDoesNotExist, Q
from django.db.models.constraints import Deferrable
from django.utils.translation import gettext, gettext_lazy as _
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from modeltrans.manager import MultilingualManager, MultilingualQuerySet
from reversion.models import Version
from wagtail.fields import RichTextField
from wagtail.models import Revision, RevisionMixin

import sentry_sdk
from autoslug.fields import AutoSlugField

from kausal_common.i18n.helpers import get_supported_languages
from kausal_common.models.language import ModelWithPrimaryLanguage
from kausal_common.models.types import MLModelManager

from aplans.utils import (
    ChoiceArrayField,
    InstancesEditableByMixin,
    InstancesVisibleForMixin,
    OrderedModel,
    PlanRelatedModelWithRevision,
    ReferenceIndexedModelMixin,
)

from indicators.models import Unit

if TYPE_CHECKING:
    from collections.abc import Sequence

    from modelcluster.fields import PK
    from wagtail.models import SerializableData

    from kausal_common.models.types import FK, RevMany
    from kausal_common.users import UserOrAnon

    from actions.attributes import AttributeType as AttributeTypeWrapper, DraftAttributes
    from images.models import AplansImage

    from .category import CategoryType
    from .plan import Plan


class AttributeTypeQuerySet(MultilingualQuerySet['AttributeType']):
    def for_categories(self, plan: Plan):
        from .category import CategoryType

        ct = ContentType.objects.get_for_model(CategoryType)
        ct_qs = CategoryType.objects.filter(plan=plan).values('id')
        f = Q(scope_content_type=ct) & Q(scope_id__in=ct_qs)
        return self.filter(f)

    def for_actions(self, plan: Plan):
        from .plan import Plan

        ct = ContentType.objects.get_for_model(Plan)
        f = Q(scope_content_type=ct) & Q(scope_id=plan.id)
        return self.filter(f)


if TYPE_CHECKING:
    _AttributeTypeManager = models.Manager.from_queryset(AttributeTypeQuerySet)

    class AttributeTypeManager(MLModelManager['AttributeType', AttributeTypeQuerySet], _AttributeTypeManager): ...

    del _AttributeTypeManager
else:
    AttributeTypeManager = MLModelManager.from_queryset(AttributeTypeQuerySet)


@reversion.register(follow=['choice_options'])
class AttributeType(
    InstancesEditableByMixin,
    InstancesVisibleForMixin,
    ReferenceIndexedModelMixin,
    ClusterableModel,
    OrderedModel,
    ModelWithPrimaryLanguage,
    PlanRelatedModelWithRevision,
):
    class AttributeFormat(models.TextChoices):
        ORDERED_CHOICE = 'ordered_choice', _('Ordered choice')
        OPTIONAL_CHOICE_WITH_TEXT = 'optional_choice', _('Optional choice with optional text')
        # TODO: combine the different choice attributes under one format
        UNORDERED_CHOICE = 'unordered_choice', _('Choice')
        TEXT = 'text', _('Text')
        RICH_TEXT = 'rich_text', _('Rich text')
        NUMERIC = 'numeric', _('Numeric')
        CATEGORY_CHOICE = 'category_choice', _('Category')

    # Model to whose instances attributes of this type can be attached
    # TODO: Enforce Action or Category
    object_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')

    # An instance that this attribute type is specific to (e.g., a plan or a category type) so that it is only shown for
    # objects within the that scope.
    # TODO: Enforce Plan or CategoryType
    scope_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    scope_id = models.PositiveIntegerField()
    scope: FK[Plan] | FK[CategoryType] = GenericForeignKey(  # pyright: ignore[reportAssignmentType]
        'scope_content_type',
        'scope_id',
    )  # type: ignore

    name = models.CharField(max_length=100, verbose_name=_('name'))
    name_i18n: str

    identifier = AutoSlugField(
        always_update=True,
        populate_from='name',
        unique_with=('object_content_type', 'scope_content_type', 'scope_id'),
    )
    help_text = models.TextField(verbose_name=_('help text'), blank=True)
    format = models.CharField[AttributeFormat, AttributeFormat](
        max_length=50,
        choices=AttributeFormat.choices,
        verbose_name=_('Format'),
        help_text=_('The format of the fields with this type'),
    )
    unit = models.ForeignKey(
        Unit,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name='+',
        verbose_name=_('Unit (only if format is numeric)'),
    )
    attribute_category_type = models.ForeignKey(
        'actions.CategoryType',
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name='+',
        verbose_name=_('Category type (if format is category)'),
        help_text=_('If the format is "Category", choose which category type the field values can be chosen from'),
    )
    show_choice_names = models.BooleanField(
        default=True,
        verbose_name=_('show choice names'),
        help_text=_('If the format is "ordered choice", determines whether the choice names are displayed'),
    )
    has_zero_option = models.BooleanField(
        default=False,
        verbose_name=_('has zero option'),
        help_text=_(
            'If the format is "ordered choice", determines whether the first option is displayed with zero bullets instead of one'
        ),
    )
    max_length = models.PositiveIntegerField(blank=True, null=True, verbose_name=_('character limit for text fields'))
    show_in_reporting_tab = models.BooleanField(default=False, verbose_name=_('show in reporting tab'))
    icon: FK[AplansImage | None] = models.ForeignKey(
        'images.AplansImage',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
        verbose_name=_('Icon'),
    )

    # Intentionally overrides ModelWithPrimaryLanguage.primary_language
    # leaving out the default keyword argument
    primary_language = models.CharField(max_length=8, choices=get_supported_languages())
    other_languages = ChoiceArrayField[list[str]](
        models.CharField[str, str](max_length=8, choices=get_supported_languages()),
        default=list,
        null=False,
        blank=True,
    )

    i18n = TranslationField(
        fields=('name', 'help_text'),
        # FIXME: This unfortunately duplicates the primary language of the plan of `scope` because we have no way of
        # easily accessing it with modeltrans. It should be kept in sync with the language of the plan of `scope`, but
        # it isn't at the moment because we hopefully will never change the primary language of a plan.
        default_language_field='primary_language_lowercase',
    )
    help_text_i18n: str

    public_fields: ClassVar = [
        'id',
        'identifier',
        'name',
        'help_text',
        'format',
        'unit',
        'attribute_category_type',
        'show_choice_names',
        'has_zero_option',
        'icon',
        'choice_options',
    ]

    objects: AttributeTypeManager = AttributeTypeManager()

    id: int
    choice_options: RevMany[AttributeTypeChoiceOption]
    choice_attributes: RevMany[AttributeChoice]

    class Meta:
        unique_together = (('object_content_type', 'scope_content_type', 'scope_id', 'identifier'),)
        verbose_name = _('field')
        verbose_name_plural = _('fields')
        ordering = ('scope_content_type', 'scope_id', 'order')

    def clean(self):
        from actions.models.action import Action

        super().clean()
        if self.unit is not None and self.format != self.AttributeFormat.NUMERIC:
            raise ValidationError({'unit': _('A unit may only be set for numeric fields.')})
        if not self.primary_language and self.other_languages:
            raise ValidationError(_('If no primary language is set, there may not be other languages.'))
        action_ct = ContentType.objects.get_for_model(Action)
        if self.instance_editability_is_action_specific and self.object_content_type != action_ct:
            raise ValidationError({'instances_editable_by': _('This value is only allowed for action fields.')})
        if self.instance_visibility_is_action_specific and self.object_content_type != action_ct:
            raise ValidationError({'instances_visible_for': _('This value is only allowed for action fields.')})
        if self.icon and not self.icon.filename.endswith('.svg'):
            raise ValidationError({'icon': _('The icon must be an SVG file.')})

    def _get_plan(self) -> Plan | None:
        if not hasattr(self, 'scope_content_type'):
            return None
        scope_app_label = self.scope_content_type.app_label
        scope_model = self.scope_content_type.model
        if scope_app_label == 'actions' and scope_model == 'plan':
            from .plan import Plan

            assert isinstance(self.scope, Plan)
            plan = self.scope
        elif scope_app_label == 'actions' and scope_model == 'categorytype':
            from .category import CategoryType

            assert isinstance(self.scope, CategoryType)
            plan = self.scope.plan
        else:
            raise Exception(f'Unexpected AttributeType scope content type {scope_app_label}:{scope_model}')
        return plan

    def save(self, *args, **kwargs):
        if not self.primary_language:
            assert not self.other_languages
            plan = self._get_plan()
            if plan is not None:
                self.primary_language = plan.primary_language
                self.other_languages = plan.other_languages
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name_i18n

    def filter_siblings(self, qs: models.QuerySet[Self, Self]) -> models.QuerySet[Self, Self]:
        return qs.filter(
            object_content_type=self.object_content_type,
            scope_content_type=self.scope_content_type,
            scope_id=self.scope_id,
        )

    def get_plans(self):
        plan = self._get_plan()
        if plan is None:
            return []
        return [plan]

    @override
    def initialize_plan_defaults(self, plan: Plan):
        # Plan defaults are encoded in the scope elsewhere
        pass


class Attribute(models.Model):
    # Must define a ParentalKey `type` in subclasses
    type: PK[AttributeType]
    # `content_object` must fit `type`
    # TODO: Enforce this
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey()
    content_type_id: int

    class Meta:
        abstract = True

    def is_visible_for_user(self, user: UserOrAnon, plan: Plan) -> bool:
        from actions.models.action import Action

        assert plan is not None
        if self.content_type_id == ContentType.objects.get_for_model(Action).id:
            action = self.content_object
        else:
            action = None
        return self.type.is_instance_visible_for(user, plan, action)  # type: ignore[attr-defined]


class AttributeTypeChoiceOptionQuerySet(MultilingualQuerySet['AttributeTypeChoiceOption']):
    def active(self) -> Self:
        return self.filter(is_active=True)

    def archived(self) -> Self:
        return self.filter(is_active=False)


if TYPE_CHECKING:

    class AttributeTypeChoiceOptionManager(
        MLModelManager['AttributeTypeChoiceOption', AttributeTypeChoiceOptionQuerySet],
    ):
        def active(self) -> AttributeTypeChoiceOptionQuerySet: ...
        def archived(self) -> AttributeTypeChoiceOptionQuerySet: ...

else:
    AttributeTypeChoiceOptionManager = MultilingualManager.from_queryset(AttributeTypeChoiceOptionQuerySet)


@reversion.register()
class AttributeTypeChoiceOption(ClusterableModel, OrderedModel):
    type: PK[AttributeType] = ParentalKey(AttributeType, on_delete=models.CASCADE, related_name='choice_options')
    name = models.CharField(max_length=100, verbose_name=_('name'))
    identifier = AutoSlugField(
        always_update=True,
        populate_from='name',
        unique_with='type',
    )
    is_active = models.BooleanField(default=True, verbose_name=_('active'))

    i18n = TranslationField(
        fields=('name',),
        default_language_field='type__primary_language_lowercase',
    )

    objects: ClassVar[AttributeTypeChoiceOptionManager] = AttributeTypeChoiceOptionManager()

    public_fields: ClassVar = ['id', 'identifier', 'name', 'is_active']

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['type', 'identifier'],
                name='unique_identifier_per_type',
            ),
            # Active rows start at order 0; archived rows are parked at
            # distinct negative orders (see `archive()`), so they coexist
            # under this single constraint.
            models.UniqueConstraint(
                fields=['type', 'order'],
                name='unique_order_per_type',
                deferrable=Deferrable.DEFERRED,
            ),
        ]
        ordering = ('type', 'order')
        verbose_name = _('attribute choice option')
        verbose_name_plural = _('attribute choice options')

    def __str__(self):
        return self.name

    def filter_siblings(self, qs: models.QuerySet[Self]) -> models.QuerySet[Self]:
        # Used by OrderedModel to make sure order starts at 0 for each
        # attribute type. Archived rows participate so that their `order`
        # slot is reserved and active inserts don't collide with them.
        return qs.filter(type=self.type)

    def archive(self) -> None:
        """
        Mark this option as archived; existing references continue to resolve.

        Bumps `order` above all sibling rows so the inline editor's
        renumbering of active options doesn't collide with this row under
        the (type, order) unique constraint.
        """
        if not self.is_active:
            return
        max_order = type(self).objects.filter(type=self.type).aggregate(
            m=models.Max('order'),
        )['m']
        self.is_active = False
        self.order = (max_order if max_order is not None else 0) + 1
        self.save(update_fields=['is_active', 'order'])

    def unarchive(self) -> None:
        """Restore this option to the active list at the end of the order."""
        if self.is_active:
            return
        max_order = type(self).objects.filter(type=self.type).aggregate(
            m=models.Max('order'),
        )['m']
        self.is_active = True
        self.order = (max_order if max_order is not None else 0) + 1
        self.save(update_fields=['is_active', 'order'])

    def is_referenced(self) -> bool:
        """
        Return True if this option is referenced anywhere that should prevent hard deletion.

        Covers:
        - Live AttributeChoice / AttributeChoiceWithText rows.
        - Wagtail revisions on the target model (drafts and historical revisions).
        - django-reversion versions of AttributeChoice / AttributeChoiceWithText
          (used by report snapshots).
        """
        fmt = self.type.format
        if fmt == AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT:
            attribute_model: type[Attribute] = AttributeChoiceWithText
            attribute_model_name = 'attributechoicewithtext'
        elif fmt in (
            AttributeType.AttributeFormat.ORDERED_CHOICE,
            AttributeType.AttributeFormat.UNORDERED_CHOICE,
        ):
            attribute_model = AttributeChoice
            attribute_model_name = 'attributechoice'
        else:
            # A choice option on a non-choice AttributeType shouldn't exist —
            # nothing can reference it through the attribute machinery.
            return False

        if attribute_model.objects.filter(choice=self).exists():
            return True

        target_ct = self.type.object_content_type
        type_key = str(self.type_id)
        pk = self.pk
        # JSONB structural containment matches only the exact attribute slot,
        # avoiding the substring false positives a `content__icontains` lookup
        # would produce (e.g. `"order": 15020` matching PK 1502). A choice
        # option belongs to one format, so only one containment shape applies.
        if fmt == AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT:
            contains_arg = {'attributes': {str(fmt): {type_key: {'choice': pk}}}}
        else:
            contains_arg = {'attributes': {str(fmt): {type_key: pk}}}
        if Revision.objects.filter(content_type=target_ct, content__contains=contains_arg).exists():
            return True

        # `serialized_data` is plain text; anchor on `,` / `}` so PK 1502
        # doesn't match `"choice": 15020`, and narrow by the owning
        # AttributeType's id so candidates from other types' history are
        # eliminated up-front. We then JSON-parse each candidate to confirm.
        type_id = self.type_id
        candidates = (
            Version.objects.filter(
                content_type__app_label='actions',
                content_type__model=attribute_model_name,
            )
            .filter(
                Q(serialized_data__contains=f'"choice": {pk},') | Q(serialized_data__contains=f'"choice": {pk}}}'),
            )
            .filter(
                Q(serialized_data__contains=f'"type": {type_id},') | Q(serialized_data__contains=f'"type": {type_id}}}'),
            )
        )

        for v in candidates.iterator():
            try:
                payload = json.loads(v.serialized_data)
            except TypeError, ValueError:
                continue
            if not isinstance(payload, list) or not payload:
                continue
            fields = payload[0].get('fields', {})
            if fields.get('choice') == pk and fields.get('type') == type_id:
                return True
        return False


@reversion.register(follow=['categories'])
class AttributeCategoryChoice(Attribute, ClusterableModel):
    type: PK[AttributeType] = ParentalKey(
        AttributeType,
        on_delete=models.CASCADE,
        related_name='category_choice_attributes',
    )
    categories = ParentalManyToManyField('actions.Category', related_name='+')

    public_fields: ClassVar = ['id', 'categories']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return '; '.join([str(c) for c in self.categories.all()])


def _attribute_choice_is_in_parent_revisions(attribute) -> bool:
    """
    Return True if a Wagtail revision of the attribute's parent references
    this `(type, choice)` pair.

    Used to recognise the publish-from-draft path: a choice option was
    archived because `is_referenced()` found it in a draft of this very
    action; publishing that draft now creates a new `AttributeChoice` with
    the archived choice, and we must allow it instead of treating it as a
    fresh selection.
    """
    content_object = attribute.content_object
    if content_object is None or not isinstance(content_object, RevisionMixin):
        return False
    target_ct = ContentType.objects.get_for_model(type(content_object))
    type_key = str(attribute.type_id)
    pk = attribute.choice_id
    fmt = attribute.type.format
    if fmt == AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT:
        contains_arg = {'attributes': {str(fmt): {type_key: {'choice': pk}}}}
    else:
        contains_arg = {'attributes': {str(fmt): {type_key: pk}}}
    return Revision.objects.filter(
        content_type=target_ct,
        object_id=str(content_object.pk),
        content__contains=contains_arg,
    ).exists()


def _validate_attribute_choice_is_assignable(attribute) -> None:
    """
    Block writes that introduce an archived choice option as a new value.

    Allowed:
    - choice is None or active.
    - choice is archived AND the row already has this exact choice (in-place
      re-save of an unchanged archived value).
    - choice is archived AND a Wagtail revision of the parent already
      references this `(type, choice)` pair — the publish-from-draft path
      legitimately materialises an option that was archived only because
      it was kept around for the draft.

    Rejected:
    - choice is archived AND the row is new (and no draft reference exists),
      or is changing to this option.

    This enforces the "no new selections of archived options" policy at the
    data layer, so any save path that runs `full_clean()` is covered — not
    just the Strawberry mutation that explicitly checks up-front.
    """
    if attribute.choice_id is None:
        return
    is_active = AttributeTypeChoiceOption.objects.filter(pk=attribute.choice_id).values_list('is_active', flat=True).first()
    if is_active is None or is_active:
        # Either the option doesn't exist (let FK validation handle it) or it
        # is still active — nothing to do.
        return
    if attribute.pk is not None:
        previous_choice_id = (
            type(attribute).objects.filter(pk=attribute.pk).values_list('choice_id', flat=True).first()
        )
        if previous_choice_id == attribute.choice_id:
            return
    if _attribute_choice_is_in_parent_revisions(attribute):
        return
    raise ValidationError(
        {'choice': _('This choice option is archived and cannot be selected as a new value.')},
    )


@reversion.register(follow=['choice'])
class AttributeChoice(Attribute):
    type: PK[AttributeType] = ParentalKey(AttributeType, on_delete=models.CASCADE, related_name='choice_attributes')
    choice = models.ForeignKey(
        AttributeTypeChoiceOption,
        on_delete=models.CASCADE,
        related_name='choice_attributes',
    )

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        try:
            choice = self.choice
        except ObjectDoesNotExist as e:
            # The choice can be missing if it has been deleted
            # but an old reference exists in a serialized revision or snapshot
            sentry_sdk.set_extra(
                'serializedReferenceError',
                'Deleted AttributeChoice instance referenced. '
                'Probable cause: serialized report representation has stale reference to choice.',
            )
            sentry_sdk.set_extra('attributeType', self.type.pk)
            sentry_sdk.set_extra('attributeChoicePk', self.choice_id)
            sentry_sdk.capture_exception(e)
            return gettext('Missing value')
        return str(choice)

    def save(self, *args, **kwargs):
        # DRF and other paths bypass full_clean() and call save() directly.
        # Enforce the archived-choice rule here so every write is covered.
        _validate_attribute_choice_is_assignable(self)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        _validate_attribute_choice_is_assignable(self)


@reversion.register(follow=['choice'])
class AttributeChoiceWithText(Attribute):
    type: PK[AttributeType] = ParentalKey(
        AttributeType,
        on_delete=models.CASCADE,
        related_name='choice_with_text_attributes',
    )
    choice = models.ForeignKey(
        AttributeTypeChoiceOption,
        blank=True,
        null=True,
        on_delete=models.CASCADE,
        related_name='choice_with_text_attributes',
    )
    text: RichTextField[str | None, str | None] = RichTextField(verbose_name=_('Text'), blank=True, null=True)
    text_i18n: str

    i18n = TranslationField(
        fields=('text',),
        default_language_field='type__primary_language_lowercase',
    )

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        text_field = cast('RichTextField', self._meta.get_field('text'))
        text = ' '.join(text_field.get_searchable_content(str(self.text_i18n))).strip()
        if len(text):
            text = f'; {text}'
        return f'{self.choice}{text}'

    def save(self, *args, **kwargs):
        _validate_attribute_choice_is_assignable(self)
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        _validate_attribute_choice_is_assignable(self)


@reversion.register()
class AttributeText(Attribute):
    type: PK[AttributeType] = ParentalKey(
        AttributeType,
        on_delete=models.CASCADE,
        related_name='text_attributes',
    )
    text = models.TextField(verbose_name=_('Text'))
    text_i18n: str

    i18n = TranslationField(
        fields=('text',),
        default_language_field='type__primary_language_lowercase',
    )

    public_fields: ClassVar = ['id', 'type', 'text']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return self.text_i18n


@reversion.register()
class AttributeRichText(Attribute):
    type: PK[AttributeType] = ParentalKey(
        AttributeType,
        on_delete=models.CASCADE,
        related_name='rich_text_attributes',
    )
    text = RichTextField(verbose_name=_('Text'))
    text_i18n: str

    i18n = TranslationField(
        fields=('text',),
        default_language_field='type__primary_language_lowercase',
    )

    public_fields: ClassVar = ['id', 'type', 'text']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        text_field = cast('RichTextField', self._meta.get_field('text'))
        return ' '.join(text_field.get_searchable_content(str(self.text_i18n)))


@reversion.register()
class AttributeNumericValue(Attribute):
    type: PK[AttributeType] = ParentalKey(AttributeType, on_delete=models.CASCADE, related_name='numeric_value_attributes')
    value = models.FloatField()

    public_fields: ClassVar = ['id', 'type', 'value']

    class Meta:
        unique_together = ('type', 'content_type', 'object_id')

    def __str__(self):
        return str(self.value)


type SetAttributeReturn = (
    tuple[Literal['create', 'delete'], Attribute] | tuple[Literal['update'], Attribute, list[str]] | tuple[None, None]
)


class ModelWithAttributes(ClusterableModel):
    """
    Fields for models with attributes.

    Models inheriting from this should implement a couple of abstract methods (see below). Unfortunately Django models
    don't get along well with the `abc` package. (Decorating with `@abstractmethod` only has an effect if deriving from
    `ABC`, which conflicts with the metaclass of `Model`.).
    """

    class Meta:
        abstract = True

    choice_attributes = GenericRelation(to='actions.AttributeChoice')
    choice_with_text_attributes = GenericRelation(to='actions.AttributeChoiceWithText')
    text_attributes = GenericRelation(to='actions.AttributeText')
    rich_text_attributes = GenericRelation(to='actions.AttributeRichText')
    numeric_value_attributes = GenericRelation(to='actions.AttributeNumericValue')
    category_choice_attributes = GenericRelation(to='actions.AttributeCategoryChoice')

    ATTRIBUTE_RELATIONS = [
        'choice_attributes',
        'choice_with_text_attributes',
        'text_attributes',
        'rich_text_attributes',
        'numeric_value_attributes',
        'category_choice_attributes',
    ]

    # Register models inheriting from this one using:
    # @reversion.register(follow=ModelWithAttributes.REVERSION_FOLLOW)
    REVERSION_FOLLOW = ATTRIBUTE_RELATIONS

    draft_attributes: DraftAttributes | None
    id: int

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.draft_attributes = None

    def get_editable_attribute_types(self, user: UserOrAnon) -> Sequence[AttributeTypeWrapper[Any]]:
        raise NotImplementedError('Implement in subclass')

    def get_visible_attribute_types(self, user: UserOrAnon) -> Sequence[AttributeTypeWrapper[Any]]:
        raise NotImplementedError('Implement in subclass')

    @classmethod
    def get_attribute_types_for_plan(
        cls, plan: Plan, only_in_reporting_tab: bool = False, unless_in_reporting_tab: bool = False
    ) -> Sequence[AttributeTypeWrapper[Any]]:
        raise NotImplementedError('Implement in subclass')

    @classmethod
    def from_serializable_data(cls, data: SerializableData, check_fks: bool = True, strict_fks: bool = False) -> Self | None:
        """Called by Wagtail when editing a draft, and by the GraphQL implementation when resolving attributes."""  # noqa: D401
        from actions.attributes import DraftAttributes

        serialized_attributes = data.pop('attributes', {})
        result = super().from_serializable_data(data, check_fks=check_fks, strict_fks=strict_fks)
        result.draft_attributes = DraftAttributes.from_revision_content(serialized_attributes, cache=getattr(data, 'cache', None))
        return result

    def _value_is_empty(self, value: dict[str, Any]) -> bool:
        return len([v for v in value.values() if v is not None or v in ('', [])]) == 0

    def set_attribute(
        self,
        attribute_type: AttributeTypeWrapper[Any],
        existing_attribute: Attribute | None,
        value_parameters: dict[str, Any],
        attribute_value_input: Any,
    ) -> SetAttributeReturn:
        if existing_attribute is None:
            if self._value_is_empty(value_parameters):
                return (None, None)

            attribute_value_class = attribute_type.VALUE_CLASS
            attribute_value = attribute_value_class.from_serialized_value(attribute_value_input)
            new_attribute = attribute_value.instantiate_attribute(attribute_type, self)
            # Validate eagerly: the deferred-operations path used by the bulk
            # REST endpoint ultimately calls QuerySet.bulk_update() /
            # bulk_create(), which bypass both save() and full_clean().
            if isinstance(new_attribute, AttributeChoice | AttributeChoiceWithText):
                _validate_attribute_choice_is_assignable(new_attribute)
            return ('create', new_attribute)
        if self._value_is_empty(value_parameters):
            return ('delete', existing_attribute)
        for k, v in value_parameters.items():
            setattr(existing_attribute, k, v)
        if isinstance(existing_attribute, AttributeChoice | AttributeChoiceWithText):
            _validate_attribute_choice_is_assignable(existing_attribute)
        return ('update', existing_attribute, list(value_parameters.keys()))

    def set_category_choice_attribute(self, attribute_type, existing_attribute, category_ids):
        if existing_attribute is None:
            if category_ids == []:
                return (None, None)
            attribute_value_class = attribute_type.VALUE_CLASS
            attribute_value = attribute_value_class.from_serialized_value(category_ids)
            new_attribute = attribute_value.instantiate_attribute(attribute_type, self)
            return ('create_and_set_related', new_attribute, 'categories', category_ids)
        if category_ids == []:
            return ('delete', existing_attribute)
        return ('set_related', existing_attribute, 'categories', category_ids)
