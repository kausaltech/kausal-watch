from django.apps import apps
from django.db import models
from django.utils.functional import lazy
from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLStreamfield, GraphQLString
from typing import Tuple, Type
from wagtail import blocks

from actions.blocks.choosers import ActionAttributeTypeChooserBlock, CategoryTypeChooserBlock
from actions.blocks.mixins import ActionListPageBlockPresenceMixin
from actions.models.action import Action
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType
from aplans.utils import underscore_to_camelcase
from reports.blocks.action_content import ReportComparisonBlock

# Attention: Defines several block classes via metaprogramming. See `action_attribute_blocks`. Currently:
# ActionLeadParagraphBlock, ActionDescriptionBlock, ActionScheduleBlock, ActionLinksBlock, ActionTasksBlock,
# ActoinMergedActionsBlock, ActionRelatedActionsBlock, ActionRelatedIndicatorsBlock, ActionContactPersonsBlock,
# ActionResponsiblePartiesBlock


def get_field_label(model: Type[models.Model], field_name: str) -> str | None:
    if not apps.ready:
        return 'label'
    field = model._meta.get_field(field_name)
    if isinstance(field, (models.ForeignObjectRel,)):
        # It's a relation field
        label = str(field.related_model._meta.verbose_name_plural).capitalize()
    else:
        label = str(field.verbose_name).capitalize()
    return label


lazy_field_label = lazy(get_field_label, str)


def generate_blocks_for_fields(model: Type[models.Model], fields: list[str | Tuple[str, dict]]):
    out = {}
    for field_name in fields:
        if isinstance(field_name, tuple):
            field_name, params = field_name
        else:
            params = {}

        camel_field = underscore_to_camelcase(field_name)
        class_name = '%s%sBlock' % (model._meta.object_name, camel_field)

        # Fields need to be evaluated lazily, because when this function is called,
        # the model registry is not yet fully initialized.
        field_label = lazy_field_label(model, field_name)
        Meta = type('Meta', (), {'label': params.get('label', field_label)})
        klass = type(class_name, (ActionListContentBlock,), {
            'Meta': Meta,
            '__module__': __name__,
        })
        register_streamfield_block(klass)
        globals()[class_name] = klass
        out[field_name] = klass
    return out


def generate_stream_block(
    name: str, all_blocks: dict[str, Type[blocks.Block]], fields: list[str | Tuple[str, blocks.Block]],
    mixins=None, extra_args=None
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
        'graphql_types': graphql_types
    })

    register_streamfield_block(block_class)
    return block_class




@register_streamfield_block
class ActionContentAttributeTypeBlock(blocks.StructBlock):
    attribute_type = ActionAttributeTypeChooserBlock(required=True)

    model_instance_container_blocks = {
        AttributeType: 'attribute_type',
    }

    graphql_fields = [
        GraphQLForeignKey('attribute_type', AttributeType, required=True)
    ]


@register_streamfield_block
class ActionContentCategoryTypeBlock(blocks.StructBlock):
    category_type = CategoryTypeChooserBlock(required=True)

    model_instance_container_blocks = {
        CategoryType: 'category_type',
    }

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType, required=True)
    ]


@register_streamfield_block
class ActionContactFormBlock(blocks.StaticBlock):
    class Meta:
        label = _("contact form")


@register_streamfield_block
class ActionOfficialNameBlock(blocks.StructBlock):
    field_label = blocks.CharBlock(
        required=False,
        help_text=_("What label should be used in the public UI for the official name?"),
        default='',
    )
    caption = blocks.CharBlock(
        required=False, help_text=_("Description to show after the field content"), default='',
    )

    graphql_fields = [
        GraphQLString('field_label'),
        GraphQLString('caption'),
    ]

    def bulk_to_python(self, values):
        # Workaround for migration from StaticBlock to StructBlock
        li = list(values)
        if len(li) == 1 and li[0] is None:
            values = [{}]
        return super().bulk_to_python(values)


class ActionListContentBlock(blocks.StaticBlock):
    block_label: str

    def get_admin_text(self):
        return _("Content block: %(label)s") % dict(label=self.label)


action_attribute_blocks = generate_blocks_for_fields(Action, [
    'lead_paragraph',
    'description',
    'schedule',
    'links',
    'tasks',
    ('merged_actions', dict(label=_('Merged actions'))),
    'related_actions',
    'related_indicators',
    'contact_persons',
    'responsible_parties',
])


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
        ('attribute', ActionContentAttributeTypeBlock(label=_('Attribute'))),
        ('categories', ActionContentCategoryTypeBlock(label=_('Category'))),
    ]
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
        ('section', ActionContentSectionBlock(required=True, label=_('Section'))),
        'lead_paragraph',
        'description',
        ('official_name', ActionOfficialNameBlock(label=_('official name'))),
        ('attribute', ActionContentAttributeTypeBlock(label=_('Attribute'))),
        ('categories', ActionContentCategoryTypeBlock(label=_('Category'))),
        'links',
        'tasks',
        'merged_actions',
        'related_actions',
        'related_indicators',
        ('contact_form', ActionContactFormBlock(required=True, label=_('Contact form'))),
        ('report_comparison', ReportComparisonBlock()),
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
        'responsible_parties',
        ('attribute', ActionContentAttributeTypeBlock(required=True, label=_('Attribute'))),
        ('categories', ActionContentCategoryTypeBlock(required=True, label=_('Category'))),
    ],
    mixins=(ActionListPageBlockPresenceMixin,),
    extra_args={
        **action_content_extra_args,
    },
)
