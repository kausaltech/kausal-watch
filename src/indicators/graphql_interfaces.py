from __future__ import annotations

import graphene


def _get_indicator_node() -> type:
    from indicators.schema import IndicatorNode

    return IndicatorNode


def _get_dimension_node() -> type:
    from indicators.schema import DimensionNode

    return DimensionNode


def _get_chart_series() -> type:
    from indicators.schema import DashboardIndicatorChartSeries

    return DashboardIndicatorChartSeries


class IndicatorBarChartInterface(graphene.Interface):
    indicator = graphene.Field(_get_indicator_node)
    dimension = graphene.Field(_get_dimension_node)
    bar_type = graphene.String()
    chart_series = graphene.List(_get_chart_series)


class IndicatorLineChartInterface(graphene.Interface):
    indicator = graphene.Field(_get_indicator_node)
    dimension = graphene.Field(_get_dimension_node)
    show_total_line = graphene.Boolean()
    chart_series = graphene.List(_get_chart_series)


class IndicatorAreaChartInterface(graphene.Interface):
    indicator = graphene.Field(_get_indicator_node)
    dimension = graphene.Field(_get_dimension_node)
    show_total_line = graphene.Boolean()
    chart_series = graphene.List(_get_chart_series)


class IndicatorPieChartInterface(graphene.Interface):
    indicator = graphene.Field(_get_indicator_node)
    dimension = graphene.Field(_get_dimension_node)
    year = graphene.Int()
    chart_series = graphene.List(_get_chart_series)


class IndicatorSummaryInterface(graphene.Interface):
    indicator = graphene.Field(_get_indicator_node)
