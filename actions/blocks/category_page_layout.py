from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString, GraphQLBoolean, GraphQLStreamfield

from actions.blocks.action_content import BaseDatasetsBlock
from actions.blocks.choosers import CategoryAttributeTypeChooserBlock, CategoryTypeDatasetSchemaChooserBlock
from actions.models.attributes import AttributeType
from budget.models import DatasetSchema


@register_streamfield_block
class CategoryPageAttributeTypeBlock(blocks.StructBlock):
    attribute_type = CategoryAttributeTypeChooserBlock(required=True)

    class Meta:
        label = _('Field')

    model_instance_container_blocks = {
        AttributeType: 'attribute_type',
    }

    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeType, required=True),
    ]


@register_streamfield_block
class CategoryPageBodyBlock(blocks.StructBlock):
    class Meta:
        label = _('Body')


@register_streamfield_block
class CategoryPageCategoryListBlock(blocks.StructBlock):
    class Meta:
        label = _('Category list')

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
    required = blocks.BooleanBlock(required=False, label=_('Required'))
    default_value = blocks.CharBlock(required=False, label=_('Default Value'))
    help_text = blocks.CharBlock(required=False, label=_('Help Text'))
    choices = blocks.StreamBlock([
        ('choice_field', FormChoiceBlock()),
    ], required=False, min_num=0, label=_('Choices'))

    class Meta:
        label = _('Form Field')

    graphql_fields = [
        GraphQLString('field_label'),
        GraphQLString('field_type'),
        GraphQLBoolean('required'),
        GraphQLString('default_value'),
        GraphQLString('help_text'),
        GraphQLStreamfield('choices'),
    ]

@register_streamfield_block
class CategoryPageContactFormBlock(blocks.StructBlock):
    heading = blocks.CharBlock(required=False, default="", label=_('Heading'))
    description = blocks.CharBlock(required=False, default="", label=_('Description'))
    fields = blocks.StreamBlock([
        ('form_field', FormFieldBlock()),
    ], required=False, min_num=0, label=_('Form Fields'))

    class Meta:
        label = _("Contact form")

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLString('description'),
        GraphQLStreamfield('fields'),
    ]


@register_streamfield_block
class CategoryTypeDatasetsBlock(BaseDatasetsBlock):
    dataset_schema = CategoryTypeDatasetSchemaChooserBlock(required=True)

    graphql_fields = BaseDatasetsBlock.graphql_fields + [
        GraphQLForeignKey('dataset_schema', DatasetSchema, required=True),
    ]

@register_streamfield_block
class CategoryPageProgressBlock(blocks.StructBlock):
    basis = blocks.ChoiceBlock(label=_('Basis'), choices=[
        ('implementation_phase', _('Implementation phase')),
        ('status', _('Status')),
    ])

    class Meta:
        label = _('Progress')


@register_streamfield_block
class CategoryPageMainTopBlock(blocks.StreamBlock):
    attribute = CategoryPageAttributeTypeBlock()
    progress = CategoryPageProgressBlock()

    graphql_types = [
        CategoryPageAttributeTypeBlock,
        CategoryPageProgressBlock,
    ]


@register_streamfield_block
class CategoryPageMainBottomBlock(blocks.StreamBlock):
    attribute = CategoryPageAttributeTypeBlock()
    body = CategoryPageBodyBlock()
    category_list = CategoryPageCategoryListBlock()
    contact_form = CategoryPageContactFormBlock()
    datasets = CategoryTypeDatasetsBlock()
    # TODO: CategoryPageSectionBlock

    graphql_types = [
        CategoryPageAttributeTypeBlock,
        CategoryPageBodyBlock,
        CategoryPageCategoryListBlock,
        CategoryPageContactFormBlock,
        CategoryTypeDatasetsBlock,
    ]


@register_streamfield_block
class CategoryPageAsideBlock(blocks.StreamBlock):
    attribute = CategoryPageAttributeTypeBlock()
    # TODO: CategoryPageSectionBlock

    graphql_types = [
        CategoryPageAttributeTypeBlock,
    ]
