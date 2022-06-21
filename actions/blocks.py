from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString
from wagtail.core import blocks

from .chooser import CategoryChooser
from .models import Category


class CategoryChooserBlock(blocks.ChooserBlock):
    @cached_property
    def target_model(self):
        return Category

    @cached_property
    def widget(self):
        return CategoryChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


@register_streamfield_block
class ActionHighlightsBlock(blocks.StaticBlock):
    pass


@register_streamfield_block
class ActionListBlock(blocks.StructBlock):
    category_filter = CategoryChooserBlock(label=_('Filter on category'))

    graphql_fields = [
        GraphQLForeignKey('category_filter', Category),
    ]


@register_streamfield_block
class CategoryListBlock(blocks.StructBlock):
    heading = blocks.CharBlock(classname='full title', label=_('Heading'), required=False)
    lead = blocks.RichTextBlock(label=_('Lead'), required=False)
    style = blocks.ChoiceBlock(choices=[
        ('cards', _('Cards')),
        ('table', _('Table')),
        ('treemap', _('Tree map')),
    ])

    graphql_fields = [
        GraphQLString('heading'),
        GraphQLString('lead'),
        GraphQLString('style'),
    ]


@register_streamfield_block
class RelatedPlanListBlock(blocks.StaticBlock):
    pass
