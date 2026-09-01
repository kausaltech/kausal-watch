from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLStreamfield, GraphQLString

from audit_logging.blocks import ChangeLogMessageBlock
from reports.blocks.report_comparison_block import ReportComparisonBlock

from .action_content_blocks import (
    ActionContactFormBlock,
    ActionContentAttributeTypeBlock,
    ActionContentCategoryTypeBlock,
    # These are here for migration compatibility
    ActionOfficialNameBlock,  # noqa: F401
    ActionResponsiblePartiesBlock,  # noqa: F401
    IndicatorCausalChainBlock,
    PlanDatasetsBlock,
)
from .stream_block import generate_stream_block

ActionContentSectionElementBlock = generate_stream_block(
    'ActionMainContentSectionElementBlock',
    fields=(
        ('attribute', ActionContentAttributeTypeBlock()),
        ('categories', ActionContentCategoryTypeBlock()),
    ),
)


@register_streamfield_block
class ActionContentSectionBlock(blocks.StructBlock):
    layout = blocks.ChoiceBlock(
        choices=[
            ('full-width', _('Full width')),
            ('grid', _('Grid')),
        ]
    )
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
        'pledges',
        ('contact_form', ActionContactFormBlock(required=True)),
        ('report_comparison', ReportComparisonBlock()),
        ('indicator_causal_chain', IndicatorCausalChainBlock()),
        ('datasets', PlanDatasetsBlock()),
        ('change_log_message', ChangeLogMessageBlock()),
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
        ('change_log_message', ChangeLogMessageBlock()),
    ],
    support_editing_from_other_form=True,
)
