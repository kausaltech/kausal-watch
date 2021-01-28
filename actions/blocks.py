from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString
from wagtail.core.blocks import ChoiceBlock, ChooserBlock, StaticBlock, StructBlock

from .chooser import CategoryChooser
from .models import Category


class CategoryChooserBlock(ChooserBlock):
    @cached_property
    def target_model(self):
        return Category

    @cached_property
    def widget(self):
        return CategoryChooser


@register_streamfield_block
class ActionHighlightsBlock(StaticBlock):
    pass


@register_streamfield_block
class ActionListBlock(StructBlock):
    category_filter = CategoryChooserBlock(label=_('Filter on category'))

    graphql_fields = [
        GraphQLForeignKey('category_filter', Category),
    ]


@register_streamfield_block
class CategoryListBlock(StructBlock):
    style = ChoiceBlock(choices=[
        ('cards', _('Cards')),
        ('table', _('Table')),
    ])

    graphql_fields = [
        GraphQLString('style'),
    ]
