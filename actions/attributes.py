from __future__ import annotations
import re
import typing
from dal import autocomplete, forward as dal_forward
from dataclasses import dataclass
from django import forms
from django.contrib.contenttypes.models import ContentType
from django.utils.html import strip_tags
from django.utils.translation import gettext_lazy as _
from html import unescape
from typing import Any, Dict, List, Optional
from wagtail.admin.panels import FieldPanel
from wagtail.fields import RichTextField
from wagtail.rich_text import RichText as WagtailRichText

import actions.models.attributes as models

if typing.TYPE_CHECKING:
    from actions.models import Plan
    from users.models import User


def html_to_plaintext(richtext):
    """
    Return a plain text version of a rich text string, suitable for search indexing;
    like Django's strip_tags, but ensures that whitespace is left between block elements
    so that <p>hello</p><p>world</p> gives "hello world", not "helloworld".
    """
    # insert space after </p>, </h1> - </h6>, </li> and </blockquote> tags
    richtext = re.sub(
        r"(</(p|h\d|li|blockquote)>)", r"\1\n\n", richtext, flags=re.IGNORECASE
    )
    richtext = re.sub(r"(<(br|hr)\s*/>)", r"\1\n", richtext, flags=re.IGNORECASE)
    return unescape(strip_tags(richtext).strip())


class AttributeFieldPanel(FieldPanel):
    pass


@dataclass
class FormField:
    attribute_type: 'AttributeType'
    django_field: forms.Field
    name: str
    label: str = ''
    # If the field refers to a modeltrans field and `language` is not empty, use localized virtual field for `language`.
    language: str = ''

    def get_panel(self):
        if self.label:
            heading = self.label
        else:
            heading = str(self.attribute_type.instance)
        if self.language:
            heading += f' ({self.language})'
        return AttributeFieldPanel(self.name, heading=heading)


class AttributeType:
    # In subclasses, define ATTRIBUTE_MODEL to be the model of the attributes of that type. It needs to have a foreign
    # key to actions.models.attributes.AttributeType called `type` with a defined `related_name`.

    @classmethod
    def from_model_instance(cls, instance: models.AttributeType):
        if instance.format == models.AttributeType.AttributeFormat.ORDERED_CHOICE:
            return OrderedChoice(instance)
        elif instance.format == models.AttributeType.AttributeFormat.CATEGORY_CHOICE:
            return CategoryChoice(instance)
        elif instance.format == models.AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT:
            return OptionalChoiceWithText(instance)
        elif instance.format == models.AttributeType.AttributeFormat.TEXT:
            return Text(instance)
        elif instance.format == models.AttributeType.AttributeFormat.RICH_TEXT:
            return RichText(instance)
        elif instance.format == models.AttributeType.AttributeFormat.NUMERIC:
            return Numeric(instance)
        raise ValueError('Unsupported attribute type format: %s' % instance.format)

    def __init__(self, instance: models.AttributeType):
        self.instance = instance

    @property
    def attributes(self):
        related_name = self.ATTRIBUTE_MODEL._meta.get_field('type').remote_field.related_name
        return getattr(self.instance, related_name)

    def get_attributes(self, obj: models.ModelWithAttributes):
        """Get the attributes of this type for the given object."""
        content_type = ContentType.objects.get_for_model(obj)
        assert content_type.app_label == 'actions'
        if content_type.model == 'action':
            assert self.instance.scope == obj.plan
        elif content_type.model == 'category':
            assert self.instance.scope == obj.type
        else:
            raise ValueError(f"Invalid content type {content_type.app_label}.{content_type.model} of object {obj}")
        return self.attributes.filter(content_type=content_type, object_id=obj.id)

    def create_attribute(self, obj: models.ModelWithAttributes, **args):
        return self.ATTRIBUTE_MODEL.objects.create(type=self.instance, content_object=obj, **args)

    def instantiate_attribute(self, obj: models.ModelWithAttributes, **args):
        return self.ATTRIBUTE_MODEL(type=self.instance, content_object=obj, **args)

    def get_form_fields(self, user: User, plan: Plan, obj: Optional[models.ModelWithAttributes] = None) -> List[FormField]:
        # Implement in subclass
        raise NotImplementedError()

    def set_attributes(self, obj: models.ModelWithAttributes, cleaned_data: Dict[str, Any]):
        """Set the attribute(s) of this type for the given object using cleaned data from a form.

        This may create new attribute model instances as well as change or delete existing ones.
        """
        # Implement in subclass
        raise NotImplementedError()

    def xlsx_values(self, attribute, related_data_objects) -> List[Any]:
        """Return the value for each of this attribute type's columns for the given attribute (can be None)."""
        raise NotImplementedError()

    def xlsx_column_labels(self) -> List[str]:
        """Return the label for each of this attribute type's columns."""
        # Override if, e.g., a certain attribute type uses more than one column
        return [str(self.instance)]

    def get_xlsx_cell_format(self) -> Optional[dict]:
        """Add a format for this attribute type to the given workbook."""
        return None


class OrderedChoice(AttributeType):
    ATTRIBUTE_MODEL = models.AttributeChoice

    @property
    def form_field_name(self):
        return f'attribute_type_{self.instance.identifier}'

    def get_form_fields(self, user: User, plan: Plan, obj: Optional[models.ModelWithAttributes] = None) -> List[FormField]:
        initial_choice = None
        if obj:
            c = self.get_attributes(obj).first()
            if c:
                initial_choice = c.choice

        choice_options = self.instance.choice_options.all()
        field = forms.ModelChoiceField(
            choice_options, initial=initial_choice, required=False, help_text=self.instance.help_text_i18n
        )
        if not self.instance.are_instances_editable_by(user, plan):
            field.disabled = True
        return [FormField(attribute_type=self, django_field=field, name=self.form_field_name)]

    def set_attributes(self, obj: models.ModelWithAttributes, cleaned_data: Dict[str, Any]):
        existing = self.get_attributes(obj)
        if existing:
            existing.delete()
        val = cleaned_data.get(self.form_field_name)
        if val is not None:
            self.create_attribute(obj, choice=val)

    def xlsx_values(self, attribute, related_data_objects) -> List[Any]:
        if not attribute:
            return [None]
        attribute_data = attribute.get('data')
        choice = next(
            (o['data']['name'] for o in related_data_objects['actions.models.attributes.AttributeTypeChoiceOption']
             if o['data']['id'] == attribute_data['choice_id']))
        return [choice]


class CategoryChoice(AttributeType):
    ATTRIBUTE_MODEL = models.AttributeCategoryChoice

    @property
    def form_field_name(self):
        return f'attribute_type_{self.instance.identifier}'

    def get_form_fields(self, user: User, plan: Plan, obj: Optional[models.ModelWithAttributes] = None) -> List[FormField]:
        from actions.models.category import Category
        initial_categories = None
        if obj:
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
                    dal_forward.Const(self.instance.attribute_category_type.id, 'type'),
                )
            ),
        )
        if not self.instance.are_instances_editable_by(user, plan):
            field.disabled = True
        return [FormField(attribute_type=self, django_field=field, name=self.form_field_name)]

    def set_attributes(self, obj: models.ModelWithAttributes, cleaned_data: Dict[str, Any]):
        existing = self.get_attributes(obj)
        if existing:
            existing.delete()
        val = cleaned_data.get(self.form_field_name)
        if val is not None:
            attribute = self.create_attribute(obj)
            attribute.categories.set(val)
            # attribute is a ClusterableModel, or at least it probably should be, so we need to call save() to
            # persist the categories we just set
            attribute.save()

    def xlsx_values(self, attribute, related_data_objects) -> List[Any]:
        category_ids = attribute['data']['categories']
        # TODO i18n doesn't really work easily with the serialized
        # models
        category_names = [
            d['data']['name']
            for d in related_data_objects['actions.models.category.Category']
            if d['data']['id'] in category_ids
        ]
        return ['; '.join(sorted(category_names))]


class OptionalChoiceWithText(AttributeType):
    ATTRIBUTE_MODEL = models.AttributeChoiceWithText

    @property
    def choice_form_field_name(self):
        return f'attribute_type_{self.instance.identifier}_choice'

    def get_text_form_field_name(self, language):
        name = f'attribute_type_{self.instance.identifier}_text'
        if language:
            name += f'_{language}'
        return name

    def get_form_fields(self, user: User, plan: Plan, obj: Optional[models.ModelWithAttributes] = None) -> List[FormField]:
        fields = []
        attribute = None
        if obj:
            attribute = self.get_attributes(obj).first()
        editable = self.instance.are_instances_editable_by(user, plan)

        # Choice
        initial_choice = None
        if attribute:
            initial_choice = attribute.choice

        choice_options = self.instance.choice_options.all()
        choice_field = forms.ModelChoiceField(
            choice_options, initial=initial_choice, required=False, help_text=self.instance.help_text_i18n
        )
        if not editable:
            choice_field.disabled = True
        fields.append(FormField(
            attribute_type=self,
            django_field=choice_field,
            name=self.choice_form_field_name,
            label=_('%(attribute_type)s (choice)') % {'attribute_type': self.instance.name_i18n},
        ))

        # Text (one field for each language)
        for language in ('', *self.instance.other_languages):
            initial_text = None
            attribute_text_field_name = f'text_{language}' if language else 'text'
            if attribute:
                initial_text = getattr(attribute, attribute_text_field_name)
            form_field_kwargs = dict(initial=initial_text, required=False, help_text=self.instance.help_text_i18n)
            if self.instance.max_length:
                form_field_kwargs.update(max_length=self.instance.max_length)
            text_field = self.ATTRIBUTE_MODEL._meta.get_field(attribute_text_field_name).formfield(**form_field_kwargs)
            if not editable:
                text_field.disabled = True
            fields.append(FormField(
                attribute_type=self,
                django_field=text_field,
                name=self.get_text_form_field_name(language),
                language=language,
                label=_('%(attribute_type)s (text)') % {'attribute_type': self.instance.name_i18n},
            ))
        return fields

    def set_attributes(self, obj: models.ModelWithAttributes, cleaned_data: Dict[str, Any]):
        existing = self.get_attributes(obj)
        if existing:
            existing.delete()
        choice_val = cleaned_data.get(self.choice_form_field_name)
        text_vals = {}
        for language in ('', *self.instance.other_languages):
            attribute_text_field_name = f'text_{language}' if language else 'text'
            text_form_field_name = self.get_text_form_field_name(language)
            text_vals[attribute_text_field_name] = cleaned_data.get(text_form_field_name)
        has_text_in_some_language = any(v for v in text_vals.values())
        if choice_val is not None or has_text_in_some_language:
            self.create_attribute(obj, choice=choice_val, **text_vals)

    def xlsx_values(self, attribute, related_data_objects) -> List[Any]:
        if not attribute:
            return [None, None]
        attribute_data = attribute.get('data')
        choice = next(
            (o['data']['name'] for o in related_data_objects['actions.models.attributes.AttributeTypeChoiceOption']
             if o['data']['id'] == attribute_data['choice_id']))
        rich_text = attribute_data['text']
        return [choice, html_to_plaintext(rich_text)]

    def xlsx_column_labels(self) -> List[str]:
        return [
            _('%(attribute_type)s (choice)') % {'attribute_type': self.instance.name_i18n},
            _('%(attribute_type)s (text)') % {'attribute_type': self.instance.name_i18n},
        ]


class TextAttributeTypeMixin:
    def get_form_field_name(self, language):
        name = f'attribute_type_{self.instance.identifier}'
        if language:
            name += f'_{language}'
        return name

    def get_form_fields(self, user: User, plan: Plan, obj: Optional[models.ModelWithAttributes] = None) -> List[FormField]:
        fields = []
        attribute = None
        if obj:
            attribute = self.get_attributes(obj).first()
        editable = self.instance.are_instances_editable_by(user, plan)

        for language in ('', *self.instance.other_languages):
            initial_text = None
            attribute_text_field_name = f'text_{language}' if language else 'text'
            if attribute:
                initial_text = getattr(attribute, attribute_text_field_name)
                # If this is a rich text field, wrap the pseudo-HTML in a RichTextObject
                # https://docs.wagtail.org/en/v5.1.1/extending/rich_text_internals.html#data-format
                if isinstance(attribute._meta.get_field(attribute_text_field_name), RichTextField):
                    initial_text = WagtailRichText(initial_text)
            form_field_kwargs = dict(initial=initial_text, required=False, help_text=self.instance.help_text_i18n)
            if self.instance.max_length:
                form_field_kwargs.update(max_length=self.instance.max_length)
            field = self.ATTRIBUTE_MODEL._meta.get_field(attribute_text_field_name).formfield(**form_field_kwargs)
            if not editable:
                field.disabled = True
            fields.append(FormField(
                attribute_type=self,
                django_field=field,
                name=self.get_form_field_name(language),
                language=language,
            ))
        return fields

    def set_attributes(self, obj: models.ModelWithAttributes, cleaned_data: Dict[str, Any]):
        text_vals = {}
        for language in ('', *self.instance.other_languages):
            attribute_text_field_name = f'text_{language}' if language else 'text'
            text_form_field_name = self.get_form_field_name(language)
            text_vals[attribute_text_field_name] = cleaned_data.get(text_form_field_name)
        has_text_in_some_language = any(v for v in text_vals.values())
        try:
            attribute = self.get_attributes(obj).get()
        except self.ATTRIBUTE_MODEL.DoesNotExist:
            if has_text_in_some_language:
                self.create_attribute(obj, **text_vals)
        else:
            if not has_text_in_some_language:
                attribute.delete()
            else:
                for field_name, value in text_vals.items():
                    setattr(attribute, field_name, value)
                attribute.save()


class Text(TextAttributeTypeMixin, AttributeType):
    ATTRIBUTE_MODEL = models.AttributeText

    def xlsx_values(self, attribute, related_data_objects) -> List[Any]:
        if not attribute:
            return [None, None]
        attribute_data = attribute.get('data')
        text = attribute_data['text']
        return [text]


class RichText(TextAttributeTypeMixin, AttributeType):
    ATTRIBUTE_MODEL = models.AttributeRichText

    def xlsx_values(self, attribute, related_data_objects) -> List[Any]:
        if not attribute:
            return [None]
        attribute_data = attribute.get('data')
        rich_text = attribute_data['text']
        return [html_to_plaintext(rich_text)]


class Numeric(AttributeType):
    ATTRIBUTE_MODEL = models.AttributeNumericValue

    @property
    def form_field_name(self):
        return f'attribute_type_{self.instance.identifier}'

    def get_form_fields(self, user: User, plan: Plan, obj: Optional[models.ModelWithAttributes] = None) -> List[FormField]:
        attribute = None
        if obj:
            attribute = self.get_attributes(obj).first()
        initial_value = None
        if attribute:
            initial_value = attribute.value
        field = forms.FloatField(initial=initial_value, required=False, help_text=self.instance.help_text_i18n)
        if not self.instance.are_instances_editable_by(user, plan):
            field.disabled = True
        return [FormField(attribute_type=self, django_field=field, name=self.form_field_name)]

    def set_attributes(self, obj: models.ModelWithAttributes, cleaned_data: Dict[str, Any]):
        val = cleaned_data.get(self.form_field_name)
        try:
            attribute = self.get_attributes(obj).get()
        except self.ATTRIBUTE_MODEL.DoesNotExist:
            if val is not None:
                self.create_attribute(obj, value=val)
        else:
            if val is None:
                attribute.delete()
            else:
                attribute.value = val
                attribute.save()

    def xlsx_column_labels(self) -> List[str]:
        return [f'{self.instance} [{self.instance.unit}]']

    def xlsx_values(self, attribute, related_data_objects) -> List[Any]:
        """Return the value for each of this attribute type's columns for the given attribute (can be None)."""
        if not attribute:
            return [None]
        return [attribute['data']['value']]

    def get_xlsx_cell_format(self) -> dict:
        return {'num_format': '#,##0.00'}
