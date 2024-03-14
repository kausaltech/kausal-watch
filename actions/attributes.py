from __future__ import annotations
import re
import typing
from abc import ABC, abstractmethod
from dal import autocomplete, forward as dal_forward
from dataclasses import dataclass
from django import forms
from django.db.models import ForeignKey, QuerySet
from django.contrib.contenttypes.models import ContentType
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _
from html import unescape
from typing import Any, Generic, TypeVar
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField
from wagtail.rich_text import RichText as WagtailRichText

import actions.models.attributes as models
from admin_site.utils import FieldLabelRenderer

if typing.TYPE_CHECKING:
    from actions.models import Category, Plan
    from reports.utils import SerializedAttributeVersion, SerializedVersion
    from users.models import User


def html_to_plaintext(richtext):
    """
    Return a plain text version of a rich text string, suitable for search indexing;
    like Django's strip_tags, but ensures that whitespace is left between block elements
    so that <p>hello</p><p>world</p> gives "hello world", not "helloworld".
    """
    # insert space after </p>, </h1> - </h6>, </li> and </blockquote> tags
    if richtext is None:
        return None
    richtext = re.sub(
        r"(</(p|h\d|li|blockquote)>)", r"\1\n\n", richtext, flags=re.IGNORECASE
    )
    richtext = re.sub(r"(<(br|hr)\s*/>)", r"\1\n", richtext, flags=re.IGNORECASE)
    return unescape(strip_tags(richtext).strip())


class AttributeFieldPanel(FieldPanel):
    pass


@dataclass
class FormField:
    plan: Plan
    attribute_type: 'AttributeType'
    django_field: forms.Field
    name: str
    label: str = ''
    # If the field refers to a modeltrans field and `language` is not empty, use localized virtual field for `language`.
    language: str = ''
    is_public: bool = False

    def get_panel(self):
        if self.label:
            heading = self.label
        else:
            heading = str(self.attribute_type.instance)
        if self.language:
            heading += f' ({self.language})'
        heading = FieldLabelRenderer(self.plan)(heading, public=self.is_public)
        return AttributeFieldPanel(self.name, heading=heading)


class AttributeValue(ABC):
    """Representation of data stored inside an Attribute instance.

    AttributeValue may sometimes contain the same data as an element of Django's dict `cleaned_data` after validation,
    but for some attribute types we need to assemble multiple values from `cleaned_data` to construct the respective
    attribute, so data stored in AttributeValue is not the same as a single value in `cleaned_data`.
    """
    @abstractmethod
    def serialize(self) -> Any:
        pass

    @abstractmethod
    def attribute_model_kwargs(self) -> dict[str, Any]:
        pass

    @abstractmethod
    def __bool__(self) -> bool:
        pass

    def instantiate_attribute(self, type: AttributeType[T], obj: models.ModelWithAttributes) -> T:
        return type.ATTRIBUTE_MODEL(type=type.instance, content_object=obj, **self.attribute_model_kwargs())



@dataclass
class OrderedChoiceAttributeValue(AttributeValue):
    option: models.AttributeTypeChoiceOption | None

    def serialize(self) -> Any:
        return self.option.pk if self.option else None

    def attribute_model_kwargs(self) -> dict[str, Any]:
        return {'choice': self.option}

    def __bool__(self):
        return self.option is not None


@dataclass
class CategoryChoiceAttributeValue(AttributeValue):
    categories: QuerySet['Category']

    def serialize(self) -> Any:
        return [c.pk for c in self.categories] if self.categories else []

    def attribute_model_kwargs(self) -> dict[str, Any]:
        return {}  # categories are set not in model's __init__() kwargs but after model instance creation

    def instantiate_attribute(self, type: AttributeType[T], obj: models.ModelWithAttributes) -> T:
        instance = super().instantiate_attribute(type, obj)
        assert isinstance(instance, models.AttributeCategoryChoice)
        instance.categories.set(self.categories)
        # instance is a ClusterableModel, or at least it probably should be, so we need to call save() if we want to
        # persist the categories we just set.
        return instance

    def __bool__(self):
        return bool(self.categories)


@dataclass
class OptionalChoiceWithTextAttributeValue(AttributeValue):
    option: models.AttributeTypeChoiceOption | None
    text_vals: dict[str, str]  # dict because we might have different strings for different languages

    def serialize(self) -> Any:
        return {
            'choice': self.option.pk if self.option else None,
            'text': self.text_vals,
        }

    def attribute_model_kwargs(self) -> dict[str, Any]:
        return {'choice': self.option, **self.text_vals}

    def __bool__(self):
        has_text_in_some_language = any(v for v in self.text_vals.values())
        return bool(self.option or has_text_in_some_language)


@dataclass
class GenericTextAttributeAttributeValue(AttributeValue):
    text_vals: dict[str, str]  # keys: "text", and zero or more "text_<language>"

    def serialize(self) -> Any:
        return self.text_vals

    def attribute_model_kwargs(self) -> dict[str, Any]:
        return self.text_vals

    def __bool__(self):
        has_text_in_some_language = any(v for v in self.text_vals.values())
        return has_text_in_some_language


@dataclass
class NumericAttributeValue(AttributeValue):
    value: float | None

    def serialize(self) -> Any:
        return self.value

    def attribute_model_kwargs(self) -> dict[str, Any]:
        return {'value': self.value}

    def __bool__(self):
        return self.value is not None


T = TypeVar('T', bound=models.Attribute)
class AttributeType(ABC, Generic[T]):
    # In subclasses, define ATTRIBUTE_MODEL to be the model of the attributes of that type. It needs to have a foreign
    # key to actions.models.attributes.AttributeType called `type` with a defined `related_name`.
    # Probably best to set it to the same value as the type variable T. Unfortunately currently we cannot get the value
    # of T without relying on CPython implementation details, so we need to repeat the value here.
    # https://stackoverflow.com/questions/57706180/generict-base-class-how-to-get-type-of-t-from-within-instance
    ATTRIBUTE_MODEL: type[T]
    instance: models.AttributeType

    @abstractmethod
    def get_form_fields(
        self,
        user: User,
        plan: Plan,
        obj: models.ModelWithAttributes | None = None,
        draft_attributes: DraftAttributes | None = None,
    ) -> list[FormField]:
        """Get form fields for this attribute type.

        There can be more than one field for an attribute type because some types contain composite information (e.g.,
        choice with text).

        If `draft_attributes` is given, its contents override the attributes attached to `obj` because it is assumed
        that the values in `draft_attributes` should be edited but are not yet committed to the model's database table.
        """
        pass

    @abstractmethod
    def get_value_from_form_data(self, cleaned_data: dict[str, Any]) -> AttributeValue | None:
        """Returns None if there is no data for this attribute type."""
        pass

    @abstractmethod
    def get_value_from_draft(self, draft_attributes: DraftAttributes) -> AttributeValue | None:
        """Returns None if there is no data for this attribute type."""
        pass

    @abstractmethod
    def xlsx_values(
        self, attribute: SerializedAttributeVersion | None, related_data_objects: dict[str, list[SerializedVersion]]
    ) -> list[Any]:
        """Return the value for each of this attribute type's columns for the given attribute (can be None)."""
        pass

    @classmethod
    def from_model_instance(cls, instance: models.AttributeType) -> AttributeType[T]:
        format_to_class: dict[models.AttributeType.AttributeFormat, type[AttributeType]] = {
            models.AttributeType.AttributeFormat.ORDERED_CHOICE: OrderedChoice,
            # We reuse the ordered choice implementation and simply render differently in the UI according to format
            # TODO: combine different choice attributes under same implementation with additional metadata configuring
            # the concrete behavior
            models.AttributeType.AttributeFormat.UNORDERED_CHOICE: OrderedChoice,
            models.AttributeType.AttributeFormat.CATEGORY_CHOICE: CategoryChoice,
            models.AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT: OptionalChoiceWithText,
            models.AttributeType.AttributeFormat.TEXT: Text,
            models.AttributeType.AttributeFormat.RICH_TEXT: RichText,
            models.AttributeType.AttributeFormat.NUMERIC: Numeric,
        }
        attr_class = format_to_class[instance.format]
        return attr_class(instance)

    def __init__(self, instance: models.AttributeType):
        self.instance = instance

    @property
    def attributes(self) -> QuerySet[T]:
        type_field = self.ATTRIBUTE_MODEL._meta.get_field('type')
        assert isinstance(type_field, ForeignKey)
        related_name = type_field.remote_field.related_name
        assert isinstance(related_name, str)
        return getattr(self.instance, related_name)

    def get_attributes(self, obj: models.ModelWithAttributes) -> QuerySet[T]:
        """Get the attributes of this type for the given object."""
        content_type = ContentType.objects.get_for_model(obj)
        assert content_type.app_label == 'actions'
        if content_type.model == 'action':
            from actions.models import Action
            assert isinstance(obj, Action)
            assert self.instance.scope == obj.plan
        elif content_type.model == 'category':
            from actions.models.category import Category
            assert isinstance(obj, Category)
            assert self.instance.scope == obj.type
        else:
            raise ValueError(f"Invalid content type {content_type.app_label}.{content_type.model} of object {obj}")
        return self.attributes.filter(content_type=content_type, object_id=obj.id)

    def create_attribute(self, obj: models.ModelWithAttributes, attribute_value: AttributeValue) -> T:
        instance = attribute_value.instantiate_attribute(type=self, obj=obj)
        instance.save()
        return instance

    def on_form_save(
        self,
        obj: models.ModelWithAttributes,
        cleaned_data: dict[str, Any],
        commit: bool = True,
    ) -> None:
        value = self.get_value_from_form_data(cleaned_data)
        if value is not None:
            if commit:
                self.commit_attribute(obj, value)
            else:
                if obj.draft_attributes is None:
                    obj.draft_attributes = DraftAttributes()
                obj.draft_attributes.update(self, value)

    def xlsx_column_labels(self) -> list[str]:
        """Return the label for each of this attribute type's columns."""
        # Override if, e.g., a certain attribute type uses more than one column
        return [str(self.instance)]

    def get_xlsx_cell_format(self) -> dict | None:
        """Add a format for this attribute type to the given workbook."""
        return None

    def commit_attribute(self, obj: models.ModelWithAttributes, attribute_value: AttributeValue) -> None:
        try:
            attribute = self.get_attributes(obj).get()
        except self.ATTRIBUTE_MODEL.DoesNotExist:
            if attribute_value:
                self.create_attribute(obj, attribute_value)
        else:
            if not attribute_value:
                attribute.delete()
            else:
                for field_name, value in attribute_value.attribute_model_kwargs().items():
                    setattr(attribute, field_name, value)
                attribute.save()

    def is_editable(self, user: User, plan: Plan, obj: models.ModelWithAttributes | None) -> bool:
        from actions.models.action import Action
        if obj is None:
            # Probably we're not editing but creating an instance of a model with attributes?
            return True
        # Depending on the object content type of the attribute type, `obj` may or may not be an action. If it is,
        # editability might depend on it, so we pass it to AttributeType.is_instance_editable_by().
        action_ct = ContentType.objects.get_for_model(Action)
        if self.instance.object_content_type == action_ct:
            assert isinstance(obj, Action)
            action = obj
        else:
            action = None
        return self.instance.is_instance_editable_by(user, plan, action)


class OrderedChoice(AttributeType[models.AttributeChoice]):
    ATTRIBUTE_MODEL = models.AttributeChoice

    @property
    def form_field_name(self):
        return f'attribute_type_{self.instance.identifier}'

    def get_form_fields(
        self,
        user: User,
        plan: Plan,
        obj: models.ModelWithAttributes | None = None,
        draft_attributes: DraftAttributes | None = None,
    ) -> list[FormField]:
        initial_choice = None
        if draft_attributes:
            attribute_value = self.get_value_from_draft(draft_attributes)
            if attribute_value is not None:
                initial_choice = attribute_value.option
        elif obj:
            c = self.get_attributes(obj).first()
            if c:
                initial_choice = c.choice

        choice_options = self.instance.choice_options.all()
        field = forms.ModelChoiceField(
            choice_options, initial=initial_choice, required=False, help_text=self.instance.help_text_i18n
        )
        if not self.is_editable(user, plan, obj):
            field.disabled = True

        is_public = self.instance.instances_visible_for == self.instance.VisibleFor.PUBLIC
        return [FormField(
            plan=plan,
            attribute_type=self,
            django_field=field,
            name=self.form_field_name,
            is_public=is_public,
        )]

    def get_value_from_form_data(self, cleaned_data: dict[str, Any]) -> OrderedChoiceAttributeValue | None:
        if self.form_field_name not in cleaned_data:
            return None
        return OrderedChoiceAttributeValue(cleaned_data.get(self.form_field_name))

    def get_value_from_draft(self, draft_attributes: DraftAttributes) -> OrderedChoiceAttributeValue | None:
        try:
            choice = draft_attributes.get_serialized_value_for_attribute_type(self)
        except KeyError:
            return None
        if choice:
            initial_choice = models.AttributeTypeChoiceOption.objects.filter(pk=choice)
            if initial_choice:
                return OrderedChoiceAttributeValue(initial_choice.get())
        return OrderedChoiceAttributeValue(None)

    def xlsx_values(
        self,
        attribute: SerializedAttributeVersion | None,
        related_data_objects: dict[str, list[SerializedVersion]],
    ) -> list[Any]:
        if not attribute:
            return [None]
        choice = next(
            (o.data['name'] for o in related_data_objects['actions.models.attributes.AttributeTypeChoiceOption']
             if o.data['id'] == attribute.data['choice_id']))
        return [choice]


class CategoryChoice(AttributeType[models.AttributeCategoryChoice]):
    ATTRIBUTE_MODEL = models.AttributeCategoryChoice

    @property
    def form_field_name(self):
        return f'attribute_type_{self.instance.identifier}'

    def get_form_fields(
        self,
        user: User,
        plan: Plan,
        obj: models.ModelWithAttributes | None = None,
        draft_attributes: DraftAttributes | None = None,
    ) -> list[FormField]:
        from actions.models.category import Category
        initial_categories = None
        if draft_attributes:
            attribute_value = self.get_value_from_draft(draft_attributes)
            if attribute_value is not None:
                initial_categories = list(attribute_value.categories)
        elif obj:
            c = self.get_attributes(obj).first()
            if c:
                initial_categories = c.categories.all()

        categories = Category.objects.filter(type=self.instance.attribute_category_type)
        field = forms.ModelMultipleChoiceField(
            categories,
            initial=initial_categories,
            required=False,
            help_text=self.instance.help_text_i18n,
            widget=autocomplete.ModelSelect2Multiple(
                url='category-autocomplete',
                forward=(
                    dal_forward.Const(self.instance.attribute_category_type.id, 'type'),  # type: ignore[union-attr]
                )
            ),
        )
        if not self.is_editable(user, plan, obj):
            field.disabled = True
        is_public = self.instance.instances_visible_for == self.instance.VisibleFor.PUBLIC
        return [FormField(
            plan=plan,
            attribute_type=self,
            django_field=field,
            name=self.form_field_name,
            is_public=is_public,
        )]

    def get_value_from_form_data(self, cleaned_data: dict[str, Any]) -> CategoryChoiceAttributeValue | None:
        if self.form_field_name not in cleaned_data:
            return None
        return CategoryChoiceAttributeValue(cleaned_data[self.form_field_name])

    def get_value_from_draft(self, draft_attributes: DraftAttributes) -> CategoryChoiceAttributeValue | None:
        from actions.models.category import Category
        try:
            category_ids = draft_attributes.get_serialized_value_for_attribute_type(self)
        except KeyError:
            return None
        return CategoryChoiceAttributeValue(Category.objects.filter(id__in=category_ids))

    def xlsx_values(
        self,
        attribute: SerializedAttributeVersion | None,
        related_data_objects: dict[str, list[SerializedVersion]],
    ) -> list[Any]:
        if not attribute:
            return [None]
        category_ids = attribute.data['categories']
        # TODO i18n doesn't really work easily with the serialized
        # models
        category_names = [
            d.data['name']
            for d in related_data_objects['actions.models.category.Category']
            if d.data['id'] in category_ids
        ]
        return ['; '.join(sorted(category_names))]


class OptionalChoiceWithText(AttributeType[models.AttributeChoiceWithText]):
    ATTRIBUTE_MODEL = models.AttributeChoiceWithText

    @property
    def choice_form_field_name(self):
        return f'attribute_type_{self.instance.identifier}_choice'

    def get_text_form_field_name(self, language):
        name = f'attribute_type_{self.instance.identifier}_text'
        if language:
            name += f'_{language}'
        return name

    def get_form_fields(
        self,
        user: User,
        plan: Plan,
        obj: models.ModelWithAttributes | None = None,
        draft_attributes: DraftAttributes | None = None,
    ) -> list[FormField]:
        draft_attribute: OptionalChoiceWithTextAttributeValue | None = None
        committed_attribute: models.AttributeChoiceWithText | None = None
        if draft_attributes:
            draft_attribute = self.get_value_from_draft(draft_attributes)
        elif obj:
            committed_attribute = self.get_attributes(obj).first()
        editable = self.is_editable(user, plan, obj)

        # Choice
        initial_choice = None
        if draft_attribute:
            initial_choice = draft_attribute.option
        elif committed_attribute:
            initial_choice = committed_attribute.choice
        choice_options = self.instance.choice_options.all()
        choice_field = forms.ModelChoiceField(
            choice_options, initial=initial_choice, required=False, help_text=self.instance.help_text_i18n
        )
        if not editable:
            choice_field.disabled = True
        is_public = self.instance.instances_visible_for == self.instance.VisibleFor.PUBLIC
        fields = [FormField(
            plan=plan,
            attribute_type=self,
            django_field=choice_field,
            name=self.choice_form_field_name,
            is_public=is_public,
            label=_('%(attribute_type)s (choice)') % {'attribute_type': self.instance.name_i18n},
        )]

        # Text (one field for each language)
        for language in ('', *self.instance.other_languages):
            initial_text = None
            attribute_text_field_name = f'text_{language}' if language else 'text'
            if draft_attribute:
                initial_text = draft_attribute.text_vals.get(attribute_text_field_name)
            elif committed_attribute:
                initial_text = getattr(committed_attribute, attribute_text_field_name)
            form_field_kwargs = dict(initial=initial_text, required=False, help_text=self.instance.help_text_i18n)
            if self.instance.max_length:
                form_field_kwargs.update(max_length=self.instance.max_length)
            text_field = self.ATTRIBUTE_MODEL._meta.get_field(attribute_text_field_name).formfield(**form_field_kwargs)  # type: ignore[union-attr]
            if not editable:
                text_field.disabled = True
                is_public = self.instance.instances_visible_for == self.instance.VisibleFor.PUBLIC
            fields.append(FormField(
                plan=plan,
                attribute_type=self,
                django_field=text_field,
                name=self.get_text_form_field_name(language),
                language=language,
                label=_('%(attribute_type)s (text)') % {'attribute_type': self.instance.name_i18n},
                is_public=is_public,
            ))
        return fields

    def get_value_from_form_data(self, cleaned_data: dict[str, Any]) -> OptionalChoiceWithTextAttributeValue | None:
        if self.choice_form_field_name not in cleaned_data and self.get_text_form_field_name('') not in cleaned_data:
            return None
        choice_val = cleaned_data[self.choice_form_field_name]
        text_vals = {}
        for language in ('', *self.instance.other_languages):
            attribute_text_field_name = f'text_{language}' if language else 'text'
            text_form_field_name = self.get_text_form_field_name(language)
            text_vals[attribute_text_field_name] = cleaned_data.get(text_form_field_name)
        return OptionalChoiceWithTextAttributeValue(choice_val, text_vals)

    def get_value_from_draft(self, draft_attributes: DraftAttributes) -> OptionalChoiceWithTextAttributeValue | None:
        try:
            serialized = draft_attributes.get_serialized_value_for_attribute_type(self)
        except KeyError:
            return None
        choice_pk = serialized.get('choice')
        try:
            choice_obj = models.AttributeTypeChoiceOption.objects.get(pk=choice_pk)
        except models.AttributeTypeChoiceOption.DoesNotExist:
            choice_obj = None
        text_vals = serialized.get('text', {})
        return OptionalChoiceWithTextAttributeValue(choice_obj, text_vals)

    def xlsx_values(
        self,
        attribute: SerializedAttributeVersion | None,
        related_data_objects: dict[str, list[SerializedVersion]],
    ) -> list[Any]:
        if not attribute:
            return [None, None]
        choice = next(
            (o.data['name'] for o in related_data_objects['actions.models.attributes.AttributeTypeChoiceOption']
             if o.data['id'] == attribute.data['choice_id']))
        rich_text = attribute.data['text']
        return [choice, html_to_plaintext(rich_text)]

    def xlsx_column_labels(self) -> list[str]:
        return [
            _('%(attribute_type)s (choice)') % {'attribute_type': self.instance.name_i18n},
            _('%(attribute_type)s (text)') % {'attribute_type': self.instance.name_i18n},
        ]


class GenericTextAttributeType(AttributeType[T]):
    def get_form_field_name(self, language):
        name = f'attribute_type_{self.instance.identifier}'
        if language:
            name += f'_{language}'
        return name

    def get_form_fields(
        self,
        user: User,
        plan: Plan,
        obj: models.ModelWithAttributes | None = None,
        draft_attributes: DraftAttributes | None = None,
    ) -> list[FormField]:
        draft_attribute: GenericTextAttributeAttributeValue | None = None
        committed_attribute: T | None = None
        if draft_attributes:
            draft_attribute = self.get_value_from_draft(draft_attributes)
        elif obj:
            committed_attribute = self.get_attributes(obj).first()
        editable = self.is_editable(user, plan, obj)

        fields = []
        for language in ('', *self.instance.other_languages):
            initial_text = None
            attribute_text_field_name = f'text_{language}' if language else 'text'
            if draft_attribute:
                initial_text = draft_attribute.text_vals.get(attribute_text_field_name)
            elif committed_attribute:
                initial_text = getattr(committed_attribute, attribute_text_field_name)
                # If this is a rich text field, wrap the pseudo-HTML in a RichTextObject
                # https://docs.wagtail.org/en/v5.1.1/extending/rich_text_internals.html#data-format
                if isinstance(committed_attribute._meta.get_field(attribute_text_field_name), RichTextField):
                    initial_text = WagtailRichText(initial_text)

            form_field_kwargs = dict(initial=initial_text, required=False, help_text=self.instance.help_text_i18n)
            if self.instance.max_length:
                form_field_kwargs.update(max_length=self.instance.max_length)
            field = self.ATTRIBUTE_MODEL._meta.get_field(attribute_text_field_name).formfield(**form_field_kwargs)
            if not editable:
                field.disabled = True
            is_public = self.instance.instances_visible_for == self.instance.VisibleFor.PUBLIC
            fields.append(FormField(
                plan=plan,
                attribute_type=self,
                django_field=field,
                name=self.get_form_field_name(language),
                language=language,
                is_public=is_public,
            ))
        return fields

    def get_value_from_form_data(self, cleaned_data: dict[str, Any]) -> GenericTextAttributeAttributeValue | None:
        if self.get_form_field_name('') not in cleaned_data:
            return None
        text_vals = {}
        for language in ('', *self.instance.other_languages):
            attribute_text_field_name = f'text_{language}' if language else 'text'
            text_form_field_name = self.get_form_field_name(language)
            text_vals[attribute_text_field_name] = cleaned_data.get(text_form_field_name)
        return GenericTextAttributeAttributeValue(text_vals)

    def get_value_from_draft(self, draft_attributes: DraftAttributes) -> GenericTextAttributeAttributeValue | None:
        try:
            values = draft_attributes.get_serialized_value_for_attribute_type(self)
        except KeyError:
            return None
        return GenericTextAttributeAttributeValue(values)


class Text(GenericTextAttributeType[models.AttributeText]):
    ATTRIBUTE_MODEL = models.AttributeText

    def xlsx_values(
        self,
        attribute: SerializedAttributeVersion | None,
        related_data_objects: dict[str, list[SerializedVersion]],
    ) -> list[Any]:
        if not attribute:
            return [None]
        text = attribute.data['text']
        return [text]


class RichText(GenericTextAttributeType[models.AttributeRichText]):
    ATTRIBUTE_MODEL = models.AttributeRichText

    def xlsx_values(
        self,
        attribute: SerializedAttributeVersion | None,
        related_data_objects: dict[str, list[SerializedVersion]],
    ) -> list[Any]:
        if not attribute:
            return [None]
        rich_text = attribute.data['text']
        return [html_to_plaintext(rich_text)]


class Numeric(AttributeType[models.AttributeNumericValue]):
    ATTRIBUTE_MODEL = models.AttributeNumericValue

    @property
    def form_field_name(self):
        return f'attribute_type_{self.instance.identifier}'

    def get_form_fields(
        self,
        user: User,
        plan: Plan,
        obj: models.ModelWithAttributes | None = None,
        draft_attributes: DraftAttributes | None = None,
    ) -> list[FormField]:
        initial_value = None
        if draft_attributes:
            attribute_value = self.get_value_from_draft(draft_attributes)
            if attribute_value is not None:
                initial_value = attribute_value.value
        elif obj:
            committed_attribute = self.get_attributes(obj).first()
            if committed_attribute:
                initial_value = committed_attribute.value
        field = forms.FloatField(initial=initial_value, required=False, help_text=self.instance.help_text_i18n)
        if not self.is_editable(user, plan, obj):
            field.disabled = True
        is_public = self.instance.instances_visible_for == self.instance.VisibleFor.PUBLIC
        return [FormField(
            plan=plan,
            attribute_type=self,
            django_field=field,
            name=self.form_field_name,
            is_public=is_public,
        )]

    def get_value_from_form_data(self, cleaned_data: dict[str, Any]) -> NumericAttributeValue | None:
        if self.form_field_name not in cleaned_data:
            return None
        return NumericAttributeValue(cleaned_data[self.form_field_name])

    def get_value_from_draft(self, draft_attributes: DraftAttributes) -> NumericAttributeValue | None:
        try:
            value = draft_attributes.get_serialized_value_for_attribute_type(self)
        except KeyError:
            return None
        return NumericAttributeValue(value)

    def xlsx_column_labels(self) -> list[str]:
        return [f'{self.instance} [{self.instance.unit}]']

    def xlsx_values(
        self,
        attribute: SerializedAttributeVersion | None,
        related_data_objects: dict[str, list[SerializedVersion]],
    ) -> list[Any]:
        """Return the value for each of this attribute type's columns for the given attribute (can be None)."""
        if not attribute:
            return [None]
        return [attribute.data['value']]

    def get_xlsx_cell_format(self) -> dict | None:
        return {'num_format': '#,##0.00'}


class DraftAttributes:
    """Contains serialized data for all draft attributes of a ModelWithAttributes instance.

    "Draft attribute" means attributes that are not necessarily commited to the model's database table yet.
    """
    _serialized_data: dict[str, Any]

    def __init__(self) -> None:
        self._serialized_data = {}

    @classmethod
    def from_revision_content(cls, data: dict[str, Any]) -> DraftAttributes:
        draft_attributes = DraftAttributes()
        draft_attributes._serialized_data = data
        return draft_attributes

    def update(self, attribute_type: AttributeType, value: AttributeValue):
        data_for_format = self._serialized_data.setdefault(str(attribute_type.instance.format), {})
        data_for_format[str(attribute_type.instance.pk)] = value.serialize()

    def get_serialized_value_for_attribute_type(self, attribute_type: AttributeType) -> Any:
        """Raises KeyError if there is no value for the given attribute type."""
        data_for_format = self._serialized_data[str(attribute_type.instance.format)]
        return data_for_format[str(attribute_type.instance.pk)]

    def get_serialized_data(self) -> dict[str, Any]:
        return self._serialized_data
