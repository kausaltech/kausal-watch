from __future__ import annotations

import typing

from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLStreamfield, GraphQLString

from actions.action_fields import action_registry
from actions.blocks.mixins import ActionListPageBlockPresenceMixin
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType
from reports.blocks.report_comparison_block import ReportComparisonBlock

from .action_content_blocks import (
    # These are here for migration compatibility
    ActionContactFormBlock,
    ActionContentAttributeTypeBlock,
    ActionContentCategoryTypeBlock,
    ActionOfficialNameBlock,  # noqa: F401
    ActionResponsiblePartiesBlock,  # noqa: F401
    IndicatorCausalChainBlock,
    PlanDatasetsBlock,
)


def generate_stream_block(
    name: str,
    fields: typing.Iterable[str | tuple[str, blocks.Block]],
    support_editing_from_other_form: bool = False,
):
    """
    Dynamically generates a stream block based on desired action fields.

    If an element in the fields iterable is a tuple, the first of the pair is the field name
    and the last of the pair is an already instantiated block that can be directly used.

    If an element is a string, the action field registry will be used to
    retrieve the correct block for that action field. (Those might be dynamically
    created classes or customized static classes.)

    If support_editing_from_other_form is True, add support to edit
    part of this block from a related model instance's edit form.
    Currently we support editing
      - an AttributeType's block from within the AttributeType's edit form and
      - a CategoryType's block from within the CategoryType's edit form.
    """
    mixins: tuple[type[typing.Any], ...] = tuple()
    extra_args = dict()

    if support_editing_from_other_form:
        mixins += (ActionListPageBlockPresenceMixin,)
        extra_args = {
            'model_instance_container_blocks': {
                AttributeType: 'attribute',
                CategoryType: 'categories',
            },
        }

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
    support_editing_from_other_form=True,
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
    support_editing_from_other_form=True,
)
