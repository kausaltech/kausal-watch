from __future__ import annotations

from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLBoolean, GraphQLForeignKey, GraphQLStreamfield, GraphQLString

from aplans.graphql_interfaces import FieldBlockMetaInterface
from aplans.utils import StaticBlockToStructBlockWorkaroundMixin

from actions.blocks.choosers import ActionAttributeTypeChooserBlock, CategoryTypeChooserBlock, PlanDatasetSchemaChooserBlock
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType
from kausal_common.budget.models import DatasetSchema


@register_streamfield_block
class ActionContentAttributeTypeBlock(blocks.StructBlock):  # block.details
    attribute_type = ActionAttributeTypeChooserBlock(required=True)
    graphql_interfaces = (FieldBlockMetaInterface, )

    class Meta:
        label = _('Field')

    model_instance_container_blocks = {
        AttributeType: 'attribute_type',
    }

    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeType, required=True),
    ]


@register_streamfield_block
class ActionContentCategoryTypeBlock(blocks.StructBlock):  # block.details
    category_type = CategoryTypeChooserBlock(required=True)
    graphql_interfaces = (FieldBlockMetaInterface, )

    class Meta:
        label = _('Category')

    model_instance_container_blocks = {
        CategoryType: 'category_type',
    }

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType, required=True),
    ]


@register_streamfield_block
class ActionResponsiblePartiesBlock(StaticBlockToStructBlockWorkaroundMixin, blocks.StructBlock):  # block.details
    graphql_interfaces = (FieldBlockMetaInterface, )

    class Meta:
        label = _('Responsible parties')

    heading = blocks.CharBlock(
        required=False, help_text=_("Heading to show instead of the default"), default='',
    )

    graphql_fields = [
        GraphQLString('heading'),
    ]

@register_streamfield_block
class FormChoiceBlock(blocks.StructBlock):  # child
    choice_label = blocks.CharBlock(required=True, label=_('Label'))
    choice_value = blocks.CharBlock(required=True, label=_('Value'))

    class Meta:
        label = _('Choice')

    graphql_fields = [
        GraphQLString('choice_label'),
        GraphQLString('choice_value'),
    ]

@register_streamfield_block
class FormFieldBlock(blocks.StructBlock):  # child
    field_label = blocks.CharBlock(required=True, label=_('Field Label'))
    field_type = blocks.ChoiceBlock(choices=[
        ('text', _('Text')),
        ('checkbox', _('Checkbox')),
        ('dropdown', _('Dropdown')),
    ], required=True, label=_('Field Type'))
    field_required = blocks.BooleanBlock(required=False, label=_('Required'))
    choices = blocks.StreamBlock([
        ('choice_field', FormChoiceBlock()),
    ], required=False, min_num=0, label=_('Choices'))

    def clean(self, value):
        cleaned_data = super().clean(value)
        field_type = cleaned_data.get('field_type')
        choices = cleaned_data.get('choices')

        errors = {}
        if field_type == 'text' and choices:
            errors['choices'] = ValidationError(_("Choices are only allowed for 'Dropdown' or 'Checkbox' field types."))

        # Check that 'choices' are provided when field_type is 'dropdown' or 'checkbox'
        if field_type in ['dropdown', 'checkbox'] and not choices:
            errors['choices'] = ValidationError(_("Choices must be provided for 'Dropdown' or 'Checkbox' field types."))

        if errors:
            raise blocks.StructBlockValidationError(errors)

        return cleaned_data

    class Meta:
        label = _('Form Field')

    graphql_fields = [
        GraphQLString('field_label'),
        GraphQLString('field_type'),
        GraphQLBoolean('field_required'),
        GraphQLStreamfield('choices'),
    ]


class BaseContactFormBlock(blocks.StructBlock):  # block.details custom
    heading = blocks.CharBlock(required=False, default="", label=_('Heading'))
    description = blocks.CharBlock(required=False, default="", label=_('Description'))
    feedback_visible = blocks.BooleanBlock(
        default=True,
        required=False,
        label=_('Feedback field visible'),
        help_text=_('Toggle visibility of the feedback field.'),
    )
    feedback_required = blocks.BooleanBlock(
        default=True,
        required=False,
        label=_('Feedback required'),
        help_text=_('Make the feedback field required when visible.'),
    )
    email_visible = blocks.BooleanBlock(
        default=True,
        required=False,
        label=_('Email field visible'),
        help_text=_('Toggle visibility of the email field.'),
    )
    email_required = blocks.BooleanBlock(
        default=True,
        required=False,
        label=_('Email required'),
        help_text=_('Make the email field required when visible.'),
    )
    fields = blocks.StreamBlock([
        ('form_field', FormFieldBlock()),
    ], required=False, min_num=0, label=_('Additional form fields'),
    help_text=_("Form fields to be shown in addition to Name, Email and Comment fields"),
    )

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLString('description'),
        GraphQLBoolean('feedback_visible'),
        GraphQLBoolean('feedback_required'),
        GraphQLBoolean('email_visible'),
        GraphQLBoolean('email_required'),
        GraphQLStreamfield('fields'),
    ]

    def clean(self, value):
        cleaned_data = super().clean(value)

        errors = {}

        if cleaned_data.get('feedback_required') and not cleaned_data.get('feedback_visible'):
            errors['feedback_required'] = ValidationError(_("Feedback can't be required if it's not visible."))

        if cleaned_data.get('email_required') and not cleaned_data.get('email_visible'):
            errors['email_required'] = ValidationError(_("Email can't be required if it's not visible."))

        if errors:
            raise blocks.StructBlockValidationError(errors)

        return cleaned_data

@register_streamfield_block
class ActionContactFormBlock(StaticBlockToStructBlockWorkaroundMixin, BaseContactFormBlock): # block.details
    graphql_interfaces = (FieldBlockMetaInterface, )
    class Meta:
        label = _("Contact form")


@register_streamfield_block
class IndicatorCausalChainBlock(blocks.StaticBlock):  # block.details.custom (into default!)  !!!
    graphql_interfaces = (FieldBlockMetaInterface, )

    class Meta:
        label = _("Indicator Causal Chain")


class BaseDatasetsBlock(blocks.StructBlock):
    heading = blocks.CharBlock(
        required=False,
        help_text=_("What heading should be used in the public UI for the dataset?"),
        default='',
        label=_("Heading"),
    )
    help_text = blocks.CharBlock(
        required=False,
        help_text=_("Help text for the Dataset to be shown in the public UI"),
        default='',
        label = _("Help text"),
    )

    class Meta:
        label = _("Datasets")

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLString('help_text'),
    ]

@register_streamfield_block
class PlanDatasetsBlock(BaseDatasetsBlock):  # block.details.custom
    dataset_schema = PlanDatasetSchemaChooserBlock(required=True)

    graphql_fields = BaseDatasetsBlock.graphql_fields + [
        GraphQLForeignKey('dataset_schema', DatasetSchema, required=True),
    ]

@register_streamfield_block
class ActionOfficialNameBlock(StaticBlockToStructBlockWorkaroundMixin, blocks.StructBlock): # block.details.custom
    graphql_interfaces = (FieldBlockMetaInterface, )

    field_label = blocks.CharBlock(
        required=False,
        help_text=_("What label should be used in the public UI for the official name?"),
        default='',
        label=_("Field label"),
    )
    caption = blocks.CharBlock(
        required=False,
        help_text=_("Description to show after the field content"),
        default='',
        label=_("Caption"),
    )

    class Meta:
        label = _('Official name')

    graphql_fields = [
        GraphQLString('field_label'),
        GraphQLString('caption'),
    ]
