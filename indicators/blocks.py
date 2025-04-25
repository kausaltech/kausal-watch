from __future__ import annotations

from django.forms import ValidationError
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.blocks import (
    BooleanBlock,
    CharBlock,
    ChoiceBlock,
    ChooserBlock,
    ListBlock,
    RichTextBlock,
    StaticBlock,
    StreamBlock,
    StructBlock,
)

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLBoolean, GraphQLForeignKey, GraphQLStreamfield, GraphQLString

from pages.blocks import PageLinkBlock

from .chooser import DimensionChooser, IndicatorChooser
from .models import Dimension, Indicator


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


class DimensionChooserBlock(ChooserBlock):
    @cached_property
    def target_model(self):
        return Dimension

    @cached_property
    def widget(self):
        return DimensionChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)

    class Meta:
        label = _('Categories')


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

    def items(self, info, values, **kwargs):
        result = []
        # Our queries from the UI unfortunately want a field `id` there that probably shouldn't exist, but let's just
        # put some crap in our response to avoid raising an error and breaking the UI.
        for value in values['indicators']:
            assert not hasattr(value, 'id')
            value.id = value['indicator'].id
            result.append(value)
        return result

    graphql_fields = [
        GraphQLString('title'),
        GraphQLStreamfield('indicators'),
        GraphQLStreamfield('items', deprecation_reason="Use 'indicators' instead"),
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


class DashboardIndicatorChartBaseBlock(StructBlock):
    """Base class for dashboard indicator chart blocks with common fields and validation."""

    help_text = CharBlock(
        required=False,
        help_text=_('Help text for the field to be shown in the UI')
    )
    indicator = IndicatorChooserBlock(
        help_text=_('Choose indicator for data visualization')
    )
    categories = DimensionChooserBlock(
        help_text=_('Choose the indicator dimension that will be used for categories in the visualization')
    )

    def clean(self, value):
        cleaned_value = super().clean(value)

        indicator = cleaned_value.get('indicator')
        dimension = cleaned_value.get('categories')

        if indicator and dimension:
            # Check if dimension is valid for this indicator
            dimension_ids = list(indicator.dimensions.values_list('dimension_id', flat=True))
            if dimension.id not in dimension_ids:
                error_msg = _("Dimension '%(dimension)s' is not valid for indicator '%(indicator)s'. "
                              "Please choose a dimension that belongs to the indicator.") % {
                    'dimension': dimension.name,
                    'indicator': indicator.name
                }
                errors = {
                    'categories': ValidationError(error_msg)
                }
                raise blocks.StructBlockValidationError(errors)

        return cleaned_value


@register_streamfield_block
class DashboardIndicatorBarChartBlock(DashboardIndicatorChartBaseBlock):
    class Meta:
        icon = 'fontawesome-chart-simple'
        label = _('Indicator Bar Chart')
        help_text = _('Indicator visualization as a bar chart')

    bar_type = ChoiceBlock(
        choices=[
            ('stacked', _('Stacked bars')),
            ('grouped', _('Grouped bars')),
        ],
        default='stacked',
        required=True
    )


@register_streamfield_block
class DashboardIndicatorLineChartBlock(DashboardIndicatorChartBaseBlock):
    class Meta:
        icon = 'fontawesome-chart-line'
        label = _('Indicator Line Chart')
        help_text = _('Indicator visualization as a line chart')

    show_total_line = BooleanBlock(
        default=False,
        required=False,
        help_text=_('Show total line')
    )


@register_streamfield_block
class DashboardIndicatorAreaChartBlock(DashboardIndicatorChartBaseBlock):
    class Meta:
        icon = 'fontawesome-chart-area'
        label = _('Indicator Area Chart')
        help_text = _('Indicator visualization as an area chart')

    show_total_line = BooleanBlock(
        default=False,
        required=False,
        help_text=_('Show total line')
    )


@register_streamfield_block
class DashboardIndicatorPieChartBlock(DashboardIndicatorChartBaseBlock):
    class Meta:
        icon = 'fontawesome-chart-pie'
        label = _('Indicator Pie Chart')
        help_text = _('Indicator visualization as a pie chart')


    show_percentages = BooleanBlock(
        default=True,
        required=False,
        help_text=_('Show percentages')
    )


@register_streamfield_block
class DashboardIndicatorSummaryBlock(StructBlock):
    class Meta:
        icon = 'list-ul'
        label = _('Indicator Summary')
        help_text = _('Indicator key figures')

    indicator = IndicatorChooserBlock(
        help_text=_('Choose indicator for data visualization')
    )


@register_streamfield_block
class DashboardParagraphBlock(StructBlock):
    text = RichTextBlock(required=True)

    class Meta:
        icon = 'doc-full'
        label = _('Paragraph')


@register_streamfield_block
class DashboardRowBlock(StructBlock):
    content = StreamBlock([
        ('bar_chart', DashboardIndicatorBarChartBlock()),
        ('line_chart', DashboardIndicatorLineChartBlock()),
        ('area_chart', DashboardIndicatorAreaChartBlock()),
        ('pie_chart', DashboardIndicatorPieChartBlock()),
        ('indicator_summary', DashboardIndicatorSummaryBlock()),
        ('paragraph', DashboardParagraphBlock()),
    ])

    class Meta:
        icon = 'fontawesome-bars-progress'
        label = _('Dashboard Row')
        help_text = _('Dashboard row with 1-3 content blocks')


@register_streamfield_block
class RelatedIndicatorsBlock(StaticBlock):
    pass
