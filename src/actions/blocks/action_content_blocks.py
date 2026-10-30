from __future__ import annotations

from typing import TYPE_CHECKING

from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLBoolean, GraphQLForeignKey, GraphQLStreamfield, GraphQLString

from kausal_common.blocks.fields import FieldBlockMetaInterface
from kausal_common.datasets.models import DatasetSchema
from kausal_common.graphene.grapple import make_grapple_streamfield

from aplans.utils import StaticBlockToStructBlockWorkaroundMixin

from actions.blocks.base import ActionContentBlockBase
from actions.blocks.choosers import ActionAttributeTypeChooserBlock, CategoryTypeChooserBlock, PlanDatasetSchemaChooserBlock
from actions.models.action import ActionTask
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise


@register_streamfield_block
class ActionContentAttributeTypeBlock(ActionContentBlockBase):  # block.details
    attribute_type = ActionAttributeTypeChooserBlock(required=True)

    class Meta:
        label = _('Field')

    model_instance_container_blocks = {
        AttributeType: 'attribute_type',
    }

    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeType, required=True),
    ]


@register_streamfield_block
class ActionContentCategoryTypeBlock(ActionContentBlockBase):  # block.details
    category_type = CategoryTypeChooserBlock(required=True)

    class Meta:
        label = _('Category')

    model_instance_container_blocks = {
        CategoryType: 'category_type',
    }

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType, required=True),
    ]


@register_streamfield_block
class ActionResponsiblePartiesBlock(ActionContentBlockBase):  # block.details
    class Meta:
        label = _('Responsible parties')

    heading = blocks.CharBlock(
        required=False,
        help_text=_('Heading to show instead of the default'),
        default='',
    )

    graphql_fields = [
        GraphQLString('heading'),
    ]


@register_streamfield_block
class ActionTaskSectionBlock(blocks.StructBlock):  # child
    """
    One section of the task list on the action page, listing the tasks in one state.

    The section's child name in `ActionTaskSectionsBlock` is the task state it lists, and the
    public UI reads it from `field`. So the states share this class, unless a state has settings
    of its own.
    """

    heading = blocks.CharBlock(
        required=False,
        help_text=_('Heading to show instead of the default'),
        default='',
        label=_('Heading'),
    )

    graphql_fields = [
        GraphQLString('heading'),
    ]


@register_streamfield_block
class ActionInProgressTaskSectionBlock(ActionTaskSectionBlock):  # child
    highlight_late_tasks = blocks.BooleanBlock(
        required=False,
        default=False,
        label=_('Highlight late tasks'),
        help_text=_('Mark the tasks whose due date has passed.'),
    )

    graphql_fields = [
        *ActionTaskSectionBlock.graphql_fields,
        GraphQLBoolean('highlight_late_tasks'),
    ]


TASK_SECTIONS: tuple[tuple[str, StrOrPromise, type[ActionTaskSectionBlock]], ...] = (
    (ActionTask.NOT_STARTED, _('Not started'), ActionTaskSectionBlock),
    (ActionTask.IN_PROGRESS, _('In progress'), ActionInProgressTaskSectionBlock),
    (ActionTask.COMPLETED, _('Completed'), ActionTaskSectionBlock),
    (ActionTask.CANCELLED, _('Cancelled'), ActionTaskSectionBlock),
)

# The sections the action page has always shown, in that order. Cancelled tasks stay hidden unless an
# admin adds their section.
DEFAULT_TASK_SECTIONS = (ActionTask.NOT_STARTED, ActionTask.IN_PROGRESS, ActionTask.COMPLETED)


class ActionTaskSectionsBlock(blocks.StreamBlock):
    def __init__(self, **kwargs):
        child_blocks = [(state, block_class(label=label)) for state, label, block_class in TASK_SECTIONS]
        # Spell out every child value: `StructBlock.normalize()` only fills in the keys it is given.
        default_values = {state: dict(block.get_default()) for state, block in child_blocks}
        kwargs.setdefault('default', [(state, default_values[state]) for state in DEFAULT_TASK_SECTIONS])
        super().__init__(child_blocks, **kwargs)

    class Meta:
        min_num = 1
        block_counts = {state: {'max_num': 1} for state, _label, _block_class in TASK_SECTIONS}


@register_streamfield_block
class ActionTasksBlock(ActionContentBlockBase):  # block.details.custom
    sections = ActionTaskSectionsBlock(
        label=_('Sections'),
        help_text=_('The task sections shown on the action page, in this order. Sections not listed are not shown.'),
    )

    graphql_fields = [
        *ActionContentBlockBase.graphql_fields,
        GraphQLStreamfield('sections'),
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
    field_type = blocks.ChoiceBlock(
        choices=[
            ('text', _('Text')),
            ('checkbox', _('Checkbox')),
            ('dropdown', _('Dropdown')),
        ],
        required=True,
        label=_('Field Type'),
    )
    field_required = blocks.BooleanBlock(required=False, label=_('Required'))
    choices = blocks.StreamBlock(
        [
            ('choice_field', FormChoiceBlock()),
        ],
        required=False,
        min_num=0,
        label=_('Choices'),
    )

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
        make_grapple_streamfield(lambda: FormFieldBlock, 'choices'),
    ]


class BaseContactFormBlock(blocks.StructBlock):  # block.details custom
    heading = blocks.CharBlock(required=False, default='', label=_('Heading'))
    description = blocks.CharBlock(required=False, default='', label=_('Description'))
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
    fields = blocks.StreamBlock(
        [
            ('form_field', FormFieldBlock()),
        ],
        required=False,
        min_num=0,
        label=_('Additional form fields'),
        help_text=_('Form fields to be shown in addition to Name, Email and Comment fields'),
    )

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLString('description'),
        GraphQLBoolean('feedback_visible'),
        GraphQLBoolean('feedback_required'),
        GraphQLBoolean('email_visible'),
        GraphQLBoolean('email_required'),
        make_grapple_streamfield(lambda: BaseContactFormBlock, 'fields'),
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
class ActionContactFormBlock(StaticBlockToStructBlockWorkaroundMixin, BaseContactFormBlock):  # block.details
    graphql_interfaces = (FieldBlockMetaInterface,)

    class Meta:
        label = _('Contact form')


@register_streamfield_block
class IndicatorCausalChainBlock(blocks.StaticBlock):  # block.details.custom (into default!)  !!!
    graphql_interfaces = (FieldBlockMetaInterface,)

    class Meta:
        label = _('Indicator Causal Chain')


class BaseDatasetsBlock(blocks.StructBlock):
    heading = blocks.CharBlock(
        required=False,
        help_text=_('What heading should be used in the public UI for the dataset?'),
        default='',
        label=_('Heading'),
    )
    help_text = blocks.CharBlock(
        required=False,
        help_text=_('Help text for the Dataset to be shown in the public UI'),
        default='',
        label=_('Help text'),
    )

    class Meta:
        label = _('Datasets')

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
class ActionOfficialNameBlock(ActionContentBlockBase):  # block.details.custom
    field_label = blocks.CharBlock(
        required=False,
        help_text=_('What label should be used in the public UI for the official name?'),
        default='',
        label=_('Field label'),
    )
    caption = blocks.CharBlock(
        required=False,
        help_text=_('Description to show after the field content'),
        default='',
        label=_('Caption'),
    )

    class Meta:
        label = _('Official name')

    graphql_fields = [
        GraphQLString('field_label'),
        GraphQLString('caption'),
    ]
