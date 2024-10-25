from __future__ import annotations

import graphene
from django.db import models
from django.forms import ValidationError
from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLBoolean, GraphQLForeignKey, GraphQLStreamfield, GraphQLString

from aplans.dynamic_blocks import generate_block_for_field
from aplans.graphql_interfaces import FieldBlockMetaInterface
from aplans.utils import StaticBlockToStructBlockWorkaroundMixin

from actions.blocks.choosers import ActionAttributeTypeChooserBlock, CategoryTypeChooserBlock, PlanDatasetSchemaChooserBlock
from actions.blocks.mixins import ActionListPageBlockPresenceMixin
from actions.models.action import Action
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType
from budget.models import DatasetSchema
from reports.blocks.report_comparison_block import ReportComparisonBlock
from reports.report_formatters import ActionTasksFormatter

# Attention: Defines several block classes via metaprogramming.
# See `action_attribute_blocks` which should currently contain:
#
# ActionContactPersonsBlock
# ActionDescriptionBlock
# ActionLeadParagraphBlock
# ActionLinksBlock
# ActionMergedActionsBlock,
# ActionRelatedActionsBlock
# ActionRelatedIndicatorsBlock
# ActionResponsiblePartiesBlock
# ActionScheduleBlock
# ActionTasksBlock


def generate_blocks_for_fields(model: type[models.Model], fields: list[str | tuple[str, dict]]):
    out = {}
    for field_name in fields:
        if isinstance(field_name, tuple):
            field_name, params = field_name
        else:
            params = {}
        klass = generate_block_for_field(model, field_name, params)
        globals()[klass.__name__] = klass
        out[field_name] = klass
    return out


def generate_stream_block(
    name: str, all_blocks: dict[str, type[blocks.Block]], fields: list[str | tuple[str, blocks.Block]],
    mixins=None, extra_args=None,
):
    if mixins is None:
        mixins = ()
    if extra_args is None:
        extra_args = {}
    field_blocks = {}
    graphql_types = list()
    for field in fields:
        if isinstance(field, tuple):
            field_name, block = field
            field_blocks[field_name] = block
        else:
            field_name = field
            block = all_blocks[field]()

        block_cls = type(block)
        if block_cls not in graphql_types:
            graphql_types.append(block_cls)
        field_blocks[field_name] = block

    block_class = type(name, (*mixins, blocks.StreamBlock), {
        '__module__': __name__,
        **field_blocks,
        **extra_args,
        'graphql_types': graphql_types,
    })

    register_streamfield_block(block_class)
    return block_class


@register_streamfield_block
class ActionContentAttributeTypeBlock(blocks.StructBlock):
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
class ActionContentCategoryTypeBlock(blocks.StructBlock):
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
class ActionResponsiblePartiesBlock(StaticBlockToStructBlockWorkaroundMixin, blocks.StructBlock):
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
class FormChoiceBlock(blocks.StructBlock):
    choice_label = blocks.CharBlock(required=True, label=_('Label'))
    choice_value = blocks.CharBlock(required=True, label=_('Value'))

    class Meta:
        label = _('Choice')

    graphql_fields = [
        GraphQLString('choice_label'),
        GraphQLString('choice_value'),
    ]

@register_streamfield_block
class FormFieldBlock(blocks.StructBlock):
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


class BaseContactFormBlock(blocks.StructBlock):
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
class ActionContactFormBlock(StaticBlockToStructBlockWorkaroundMixin, BaseContactFormBlock):
    graphql_interfaces = (FieldBlockMetaInterface, )
    class Meta:
        label = _("Contact form")

@register_streamfield_block
class IndicatorCausalChainBlock(blocks.StaticBlock):
    graphql_interfaces = (FieldBlockMetaInterface, )

    class Meta:
        label = _("Indicator Causal Chain")


class BaseDatasetsBlock(blocks.StructBlock):
    heading = blocks.CharBlock(
        required=False,
        help_text=_("What heading should be used in the public UI for the Dataset?"),
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
class PlanDatasetsBlock(BaseDatasetsBlock):
    dataset_schema = PlanDatasetSchemaChooserBlock(required=True)

    graphql_fields = BaseDatasetsBlock.graphql_fields + [
        GraphQLForeignKey('dataset_schema', DatasetSchema, required=True),
    ]

@register_streamfield_block
class ActionOfficialNameBlock(StaticBlockToStructBlockWorkaroundMixin, blocks.StructBlock):
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


action_attribute_blocks = generate_blocks_for_fields(Action, [
    ('lead_paragraph', {'label': _('Lead paragraph')}),
    'description',
    'schedule',
    'links',
    ('tasks', {'report_value_formatter_class': ActionTasksFormatter}),
    ('merged_actions', {'label': _('Merged actions')}),
    ('related_actions', {'label': _('Related actions')}),
    ('dependencies', {'label': _('Action dependencies')}),
    'related_indicators',
    'contact_persons',
])


def get_action_block_for_field(field_name):
    global action_attribute_blocks
    if field_name in action_attribute_blocks:
        return action_attribute_blocks[field_name]
    klass = generate_block_for_field(Action, field_name)
    globals()[klass.__name__] = klass
    return klass


action_content_extra_args = {
    'model_instance_container_blocks': {
        AttributeType: 'attribute',
        CategoryType: 'categories',
    },
}

ActionContentSectionElementBlock = generate_stream_block(
    'ActionMainContentSectionElementBlock',
    action_attribute_blocks,
    fields = [
        ('attribute', ActionContentAttributeTypeBlock()),
        ('categories', ActionContentCategoryTypeBlock()),
    ],
)


@register_streamfield_block
class ActionContentSectionBlock(blocks.StructBlock):
    layout = blocks.ChoiceBlock(choices=[
        ('full-width', _('Full width')),
        ('grid', _('Grid')),
    ])
    heading = blocks.CharBlock(classname='full title', label=_('Heading'), required=False)
    help_text = blocks.CharBlock(label=_('Help text'), required=False)
    blocks = ActionContentSectionElementBlock(label=_('Blocks'))

    class Meta:
        label = _('Section')

    graphql_fields = [
        GraphQLString('layout'),
        GraphQLString('heading'),
        GraphQLString('help_text'),
        GraphQLStreamfield('blocks'),
    ]


ActionMainContentBlock = generate_stream_block(
    'ActionMainContentBlock',
    action_attribute_blocks,
    fields=[
        ('section', ActionContentSectionBlock(required=True)),
        'lead_paragraph',
        'description',
        ('official_name', ActionOfficialNameBlock()),
        ('attribute', ActionContentAttributeTypeBlock()),
        ('categories', ActionContentCategoryTypeBlock()),
        'links',
        'tasks',
        'merged_actions',
        'related_actions',
        'dependencies',
        'related_indicators',
        ('contact_form', ActionContactFormBlock(required=True)),
        ('report_comparison', ReportComparisonBlock()),
        ('indicator_causal_chain', IndicatorCausalChainBlock()),
        ('datasets', PlanDatasetsBlock()),
    ],
    mixins=(ActionListPageBlockPresenceMixin,),
    extra_args={
        **action_content_extra_args,
    },
)

ActionAsideContentBlock = generate_stream_block(
    'ActionAsideContentBlock',
    action_attribute_blocks,
    fields=[
        'schedule',
        'contact_persons',
        ('responsible_parties', ActionResponsiblePartiesBlock(required=True)),
        ('attribute', ActionContentAttributeTypeBlock(required=True)),
        ('categories', ActionContentCategoryTypeBlock(required=True)),
    ],
    mixins=(ActionListPageBlockPresenceMixin,),
    extra_args={
        **action_content_extra_args,
    },
)
