from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey
from wagtail import blocks

from actions.blocks.choosers import CategoryChooserBlock
from actions.models.category import Category


@register_streamfield_block
class ActionHighlightsBlock(blocks.StaticBlock):
    class Meta:
        label = _('Action highlights')


@register_streamfield_block
class ActionListBlock(blocks.StructBlock):
    category_filter = CategoryChooserBlock(label=_('Filter on category'))

    class Meta:
        label = _('Action list')

    graphql_fields = [
        GraphQLForeignKey('category_filter', Category),
    ]


