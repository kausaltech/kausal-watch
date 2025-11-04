from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLString


@register_streamfield_block
class PathsOutcomeBlock(blocks.StructBlock):
    heading = blocks.CharBlock(
        required=False,
        help_text=_("What heading should be used in the public UI for the Outcome?"),
        default='',
        label=_("Heading"),
    )
    help_text = blocks.CharBlock(
        required=False,
        help_text=_("Help text for the Outcome to be shown in the public UI"),
        default='',
        label = _("Help text"),
    )

    outcome_node_id = blocks.CharBlock(
        max_length=200, required=True, verbose_name=_('Kausal Paths outcome node ID'),
        help_text=_('Kausal Paths outcome node to be used'),
    )

    class Meta:
        label = _("Paths outcome")

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLString('help_text'),
        GraphQLString('outcome_node_id'),
    ]

