from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString

from actions.blocks.choosers import CategoryChooserBlock, CategoryLevelChooserBlock
from actions.models.category import Category, CategoryLevel


@register_streamfield_block
class ActionHighlightsBlock(blocks.StaticBlock):
    class Meta:
        label = _('Action highlights')


@register_streamfield_block
class ActionListBlock(blocks.StructBlock):
    heading = blocks.CharBlock(
        required=False,
        help_text=_('What heading should be used in the public UI for the Action list?'),
        default='',
        label=_('Heading'),
    )
    help_text = blocks.CharBlock(
        required=False,
        help_text=_('Help text for the Action list to be shown in the public UI'),
        default='',
        label=_('Help text'),
    )

    category_filter = CategoryChooserBlock(label=_('Filter on category'))
    group_by_category_level = CategoryLevelChooserBlock(
        required=False,
        label=_('Group by level'),
        help_text=_('Use category level for tabbed grouping in the public UI'),
    )

    class Meta:
        label = _('Action list')

    graphql_fields = [
        GraphQLForeignKey('category_filter', Category),
        GraphQLString('heading', required=False),
        GraphQLString('help_text', required=False),
        GraphQLForeignKey('group_by_category_level', CategoryLevel, required=False),
    ]
