from __future__ import annotations

from django.utils.translation import gettext_lazy as _

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey

from actions.blocks.choosers import ActionAttributeTypeChooserBlock
from actions.models.attributes import AttributeType

from .column_block_base import ColumnBlockBase
from .stream_block import generate_stream_block


@register_streamfield_block
class FieldColumnBlock(ColumnBlockBase):
    attribute_type = ActionAttributeTypeChooserBlock()
    class Meta:
        label = _("Field")

    graphql_fields = ColumnBlockBase.graphql_fields + [
        GraphQLForeignKey('attribute_type', AttributeType),
    ]


ActionDashboardColumnBlock = generate_stream_block(
    'ActionDashboardColumnBlock',
    fields = (
        'identifier',
        'name',
        'impact',  # TODO: deprecate
        'implementation_phase',
        'status',
        'tasks',
        'responsible_parties',
        'updated_at',
        'start_date',
        'end_date',
        ('fields', 'attribute'),
        ('indicators', 'related_indicators'),
        ('organization', 'primary_org'),
    ),
    support_editing_from_other_form=False,
    block_type='dashboard',
)
