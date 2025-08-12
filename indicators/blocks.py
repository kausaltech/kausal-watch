from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.forms import ValidationError
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail import blocks
from wagtail.blocks import (
    BooleanBlock,
    CharBlock,
    ChoiceBlock,
    ChooserBlock,
    IntegerBlock,
    ListBlock,
    RichTextBlock,
    StaticBlock,
    StreamBlock,
    StructBlock,
)

from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLBoolean, GraphQLField, GraphQLForeignKey, GraphQLInt, GraphQLStreamfield, GraphQLString

from pages.blocks import PageLinkBlock

from .chooser import DimensionChooser, IndicatorChooser
from .models import Dimension, Indicator

if TYPE_CHECKING:
    from kausal_common.graphene import GQLInfo

    from .schema import DashboardIndicatorChartSeries


class IndicatorChooserBlock(ChooserBlock[Indicator]):
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


class DimensionChooserBlock(ChooserBlock[Dimension]):
    @cached_property
    def target_model(self):
        return Dimension

    @cached_property
    def widget(self):
        return DimensionChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)

    class Meta:
        label = _('Dimension')


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


def _get_dashboard_indicator_chart_series_class() -> type[DashboardIndicatorChartSeries]:
    from .schema import DashboardIndicatorChartSeries
    return DashboardIndicatorChartSeries


class DashboardIndicatorChartBaseBlock(StructBlock):
    """Base class for dashboard indicator chart blocks with common fields and validation."""

    help_text = CharBlock(
        required=False,
        help_text=_('Help text for the field to be shown in the UI')
    )
    indicator = IndicatorChooserBlock(
        help_text=_('Choose the indicator for data visualization')
    )
    dimension = DimensionChooserBlock(
        help_text=_('Choose the indicator dimension that will be used for categories in the visualization'),
        required=False
    )

    graphql_fields = [
        GraphQLString('help_text'),
        GraphQLForeignKey('indicator', Indicator),
        GraphQLForeignKey('dimension', Dimension),
        GraphQLField(
            'chart_series',
            _get_dashboard_indicator_chart_series_class,
            is_list=True,
        ),
    ]

    def chart_series(self, info: GQLInfo, values: dict[str, Any]) -> list[DashboardIndicatorChartSeries]:
        from .schema import DashboardIndicatorChartSeries
        indicator = values['indicator']
        assert isinstance(indicator, Indicator)
        dimension = values['dimension']
        assert isinstance(dimension, Dimension | None)
        categories = dimension.categories.all() if dimension else [None]
        return [
            DashboardIndicatorChartSeries(
                dimension_category=category,
                values=indicator.values.filter(categories=category),
            )
            for category in categories
        ]

    def clean(self, value):
        cleaned_value = super().clean(value)

        indicator = cleaned_value.get('indicator')
        dimension = cleaned_value.get('dimension')

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
                    'dimension': ValidationError(error_msg)
                }
                raise blocks.StructBlockValidationError(errors)

        return cleaned_value


@register_streamfield_block
class DashboardIndicatorBarChartBlock(DashboardIndicatorChartBaseBlock):
    bar_type = ChoiceBlock(
        choices=[
            ('stacked', _('Stacked bars')),
            ('grouped', _('Grouped bars')),
        ],
        default='stacked',
        required=True
    )

    graphql_fields = DashboardIndicatorChartBaseBlock.graphql_fields + [
        GraphQLString('bar_type'),
    ]

    class Meta:
        icon = 'fontawesome-chart-simple'
        label = _('Indicator: Bar Chart')
        help_text = _('Indicator visualization as a bar chart')


@register_streamfield_block
class DashboardIndicatorLineChartBlock(DashboardIndicatorChartBaseBlock):
    show_total_line = BooleanBlock(
        default=False,
        required=False,
        help_text=_('Show total line')
    )

    graphql_fields = DashboardIndicatorChartBaseBlock.graphql_fields + [
        GraphQLBoolean('show_total_line'),
    ]

    class Meta:
        icon = 'fontawesome-chart-line'
        label = _('Indicator: Line Chart')
        help_text = _('Indicator visualization as a line chart')


@register_streamfield_block
class DashboardIndicatorAreaChartBlock(DashboardIndicatorChartBaseBlock):
    show_total_line = BooleanBlock(
        default=False,
        required=False,
        help_text=_('Show total line')
    )

    graphql_fields = DashboardIndicatorChartBaseBlock.graphql_fields + [
        GraphQLBoolean('show_total_line'),
    ]

    class Meta:
        icon = 'fontawesome-chart-area'
        label = _('Indicator: Area Chart')
        help_text = _('Indicator visualization as an area chart')


@register_streamfield_block
class DashboardIndicatorPieChartBlock(DashboardIndicatorChartBaseBlock):
    year: IntegerBlock = IntegerBlock(
        required=True,
        help_text=_('Enter the year you want to visualize'),
    )

    graphql_fields = DashboardIndicatorChartBaseBlock.graphql_fields + [
        GraphQLInt('year'),
    ]

    class Meta:
        icon = 'fontawesome-chart-pie'
        label = _('Indicator: Pie Chart')
        help_text = _('Indicator visualization as a pie chart')

    def clean(self, value):
        cleaned_value = super().clean(value)

        indicator = cleaned_value.get('indicator')
        year_value = cleaned_value.get('year')

        if indicator and year_value is not None:
            selected_year = year_value

            available_years = set()
            values = indicator.values.all()
            for val in values:
                value_date = val.date
                available_years.add(value_date.year)

            if len(available_years) > 0 and selected_year not in available_years:
                years_str = ", ".join(str(year) for year in sorted(available_years))
                error_msg = _("The selected year (%(selected_year)s) has no data for this indicator. "
                              "Available years are: %(available_years)s") % {
                    'selected_year': selected_year,
                    'available_years': years_str
                }
                errors = {
                    'year': ValidationError(error_msg)
                }
                raise blocks.StructBlockValidationError(errors)

        return cleaned_value


@register_streamfield_block
class DashboardIndicatorSummaryBlock(StructBlock):
    indicator = IndicatorChooserBlock(
        help_text=_('Choose the indicator for data visualization')
    )

    graphql_fields = [
        GraphQLForeignKey('indicator', Indicator),
    ]

    class Meta:
        icon = 'list-ul'
        label = _('Indicator: Summary')
        help_text = _('Indicator key figures')


@register_streamfield_block
class DashboardParagraphBlock(StructBlock):
    text = RichTextBlock(
        required=True
    )

    graphql_fields = [
        GraphQLString('text'),
    ]

    class Meta:
        icon = 'doc-full'
        label = _('Paragraph')


@register_streamfield_block
class DashboardRowBlock(StreamBlock):
    bar_chart = DashboardIndicatorBarChartBlock()
    line_chart = DashboardIndicatorLineChartBlock()
    area_chart = DashboardIndicatorAreaChartBlock()
    pie_chart = DashboardIndicatorPieChartBlock()
    indicator_summary = DashboardIndicatorSummaryBlock()
    paragraph = DashboardParagraphBlock()

    # The following would make DashboardRowBlock work for streamfields that consist only of instances of this block. But
    # we want to use it alongside blocks of other types, in which case adding `graphql_types` would lead to an error.
    # Apparently you can't use the same block type in both ways. Might be due to the GraphQL specification.
    # graphql_types = [
    #     DashboardIndicatorBarChartBlock,
    #     DashboardIndicatorLineChartBlock,
    #     DashboardIndicatorAreaChartBlock,
    #     DashboardIndicatorPieChartBlock,
    #     DashboardIndicatorSummaryBlock,
    #     DashboardParagraphBlock,
    # ]

    class Meta:
        icon = 'fontawesome-bars-progress'
        label = _('Dashboard Row')
        help_text = _('Dashboard row with 1-3 content blocks')
        min_num = 1
        max_num = 3


@register_streamfield_block
class RelatedIndicatorsBlock(StaticBlock):
    pass
