from django.utils.functional import cached_property
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLStreamfield, GraphQLString
from wagtail.core.blocks import (CharBlock, ChoiceBlock, ChooserBlock, ListBlock, RichTextBlock, StaticBlock,
                                 StructBlock)

from .chooser import IndicatorChooser
from .models import Indicator
from pages.blocks import PageLinkBlock


class IndicatorChooserBlock(ChooserBlock):
    @cached_property
    def target_model(self):
        return Indicator

    @cached_property
    def widget(self):
        return IndicatorChooser

    def render_basic(self, value, context=None):
        if value:
            return format_html('<a href="{0}">{1}</a>', '', value.name)
        else:
            return ''

    class Meta:
        label = _('Indicator')


@register_streamfield_block
class IndicatorHighlightsBlock(StaticBlock):
    pass


@register_streamfield_block
class IndicatorBlock(StructBlock):
    indicator = IndicatorChooserBlock(label=_('Indicator'))
    style = ChoiceBlock(choices=[
        ('graph', _('Graph')),
        ('progress', _('Progress')),
        ('animated', _('Animated')),
    ])

    graphql_fields = [
        GraphQLForeignKey('indicator', Indicator),
        GraphQLString('style'),
    ]

    class Meta:
        label = _('Indicator')


@register_streamfield_block
class IndicatorGroupBlock(ListBlock):
    def __init__(self, **kwargs):
        super().__init__(IndicatorBlock, **kwargs)

    class Meta:
        label = _('Indicators')


@register_streamfield_block
class IndicatorShowcaseBlock(StructBlock):
    title = CharBlock(required=False)
    body = RichTextBlock(required=False)
    indicator = IndicatorChooserBlock()
    link_button = PageLinkBlock()
    # FIXME: I'd like to make `link_button` optional, but the argument `required` has no effect here. See comment in
    # PageLinkBlock.

    graphql_fields = [
        GraphQLString('title'),
        GraphQLString('body'),
        GraphQLForeignKey('indicator', Indicator),
        GraphQLStreamfield('link_button', is_list=False),
    ]


@register_streamfield_block
class RelatedIndicatorsBlock(StaticBlock):
    pass
