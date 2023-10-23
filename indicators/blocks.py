from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLBoolean, GraphQLForeignKey, GraphQLStreamfield, GraphQLString
from wagtail.blocks import (
    BooleanBlock, CharBlock, ChoiceBlock, ChooserBlock, ListBlock, RichTextBlock, StaticBlock, StructBlock
)

from .chooser import IndicatorChooser
from .models import Indicator
from pages.blocks import PageLinkBlock


class IndicatorChooserBlock(ChooserBlock):
    @cached_property
    def target_model(self):
        return Indicator

    @cached_property
    def widget(self):
        return IndicatorChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)

    class Meta:
        label = _('Indicator')


@register_streamfield_block
class IndicatorHighlightsBlock(StaticBlock):
    class Meta:
        label = _('Indicator highlights')



@register_streamfield_block
class IndicatorBlock(StructBlock):
    indicator = IndicatorChooserBlock()
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
class IndicatorGroupBlock(StructBlock):
    title = CharBlock(required=False)
    indicators = ListBlock(IndicatorBlock())

    graphql_fields = [
        GraphQLString('title'),
        GraphQLStreamfield('indicators'),
    ]

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
    indicator_is_normalized = BooleanBlock(required=False)

    class Meta:
        label = _('Indicator showcase')

    graphql_fields = [
        GraphQLString('title'),
        GraphQLString('body'),
        GraphQLForeignKey('indicator', Indicator),
        GraphQLStreamfield('link_button', is_list=False),
        GraphQLBoolean('indicator_is_normalized'),
    ]


@register_streamfield_block
class RelatedIndicatorsBlock(StaticBlock):
    pass
