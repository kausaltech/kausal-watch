from __future__ import annotations

from django.utils.translation import gettext_lazy as _
import typing
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLStreamfield, GraphQLString

from actions.blocks.mixins import ActionListPageBlockPresenceMixin
from actions.action_fields import action_registry
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType
from reports.blocks.report_comparison_block import ReportComparisonBlock
from .action_content_blocks import (
    PlanDatasetsBlock,
    IndicatorCausalChainBlock,
    ActionContactFormBlock,
    ActionContentAttributeTypeBlock,
    ActionContentCategoryTypeBlock,
)


# def generate_blocks_for_fields(model: type[models.Model], fields: list[str | tuple[str, dict]]):
#     out = {}
#     for field_name in fields:
#         if isinstance(field_name, tuple):
#             field_name, params = field_name
#         else:
#             params = {}
#         klass = generate_block_for_field(model, field_name, params)
#         globals()[klass.__name__] = klass
#         out[field_name] = klass
#     return out


def generate_stream_block(
    name: str, fields: typing.Iterable[str | tuple[str, blocks.Block]],
    mixins: tuple[type[blocks.Block], ...] = tuple(),
    extra_args=None,
):
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
            block = action_registry.get_details_block(field_name)

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


# action_attribute_blocks = generate_blocks_for_fields(Action, [
#     ('lead_paragraph', {'label': _('Lead paragraph')}),                 # blocks.details.default
#     'description',                                                      # blocks.details.default
#     'schedule',                                                         # blocks.details.default
#     'links',                                                            # blocks.details.default
#     ('tasks', {'report_value_formatter_class': ActionTasksFormatter}),  # blocks.details.default (custom formatter!)
#     ('merged_actions', {'label': _('Merged actions')}),                 # blocks.details.default
#     ('related_actions', {'label': _('Related actions')}),               # blocks.details.default
#     ('dependencies', {'label': _('Action dependencies')}),              # blocks.details.default
#     'related_indicators',                                               # blocks.details.default
#     'contact_persons',                                                  # blocks.details.default
# ])

# def get_action_block_for_field(field_name):  # blocks.report called from there!
#     if field_name in action_attribute_blocks:
#         return action_attribute_blocks[field_name]
#     klass = generate_block_for_field(Action, field_name)
#     globals()[klass.__name__] = klass
#     return klass


ActionContentSectionElementBlock = generate_stream_block(
    'ActionMainContentSectionElementBlock',
    fields = (
        ('attribute', ActionContentAttributeTypeBlock()),
        ('categories', ActionContentCategoryTypeBlock()),
    ),
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


action_content_extra_args = {
    'model_instance_container_blocks': {
        AttributeType: 'attribute',
        CategoryType: 'categories',
    },
}


ActionMainContentBlock = generate_stream_block(
    'ActionMainContentBlock',
    fields=(
        ('section', ActionContentSectionBlock(required=True)),
        'lead_paragraph',
        'description',
        'official_name',
        'attribute',
        'categories',
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
    ),
    mixins=(ActionListPageBlockPresenceMixin,),
    extra_args={
        **action_content_extra_args,
    },
)

ActionAsideContentBlock = generate_stream_block(
    'ActionAsideContentBlock',
    fields=[
        'schedule',
        'contact_persons',
        'responsible_parties',
        'attribute',
        'categories',
    ],
    mixins=(ActionListPageBlockPresenceMixin,),
    extra_args={
        **action_content_extra_args,
    },
)
