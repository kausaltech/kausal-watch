from __future__ import annotations

import datetime

from django.core.exceptions import ValidationError

import pytest

from indicators.models.indicator import VisualizationType
from indicators.schema import compute_chart_series
from indicators.tests.factories import (
    DimensionCategoryFactory,
    DimensionFactory,
    IndicatorDimensionFactory,
    IndicatorFactory,
    IndicatorLevelFactory,
    IndicatorValueFactory,
)

pytestmark = pytest.mark.django_db


def test_compute_chart_series_without_dimension():
    """compute_chart_series returns a single series with all values when no dimension is given."""

    indicator = IndicatorFactory.create()
    IndicatorValueFactory.create(indicator=indicator, value=1.0, date=datetime.date(2020, 1, 1))
    IndicatorValueFactory.create(indicator=indicator, value=2.0, date=datetime.date(2021, 1, 1))

    series = compute_chart_series(indicator, dimension=None)
    assert len(series) == 1
    assert series[0].dimension_category is None


def test_compute_chart_series_with_dimension():
    """compute_chart_series returns one series per category when a dimension is given."""

    indicator = IndicatorFactory.create()
    dimension = DimensionFactory.create()
    IndicatorDimensionFactory.create(indicator=indicator, dimension=dimension)
    cat_a = DimensionCategoryFactory.create(dimension=dimension, name='A')
    cat_b = DimensionCategoryFactory.create(dimension=dimension, name='B')
    IndicatorValueFactory.create(indicator=indicator, value=1.0, date=datetime.date(2020, 1, 1), categories=[cat_a])
    IndicatorValueFactory.create(indicator=indicator, value=2.0, date=datetime.date(2020, 1, 1), categories=[cat_b])

    series = compute_chart_series(indicator, dimension=dimension)
    assert len(series) == 2
    category_names = {s.dimension_category.name for s in series}
    assert category_names == {'A', 'B'}


def test_indicator_accepts_visualization_type():
    """Indicator should accept visualization_type and bar_type fields."""

    indicator = IndicatorFactory.create(
        visualization_type=VisualizationType.BAR_CHART,
        bar_type='stacked',
    )
    indicator.refresh_from_db()
    assert indicator.visualization_type == 'bar_chart'
    assert indicator.bar_type == 'stacked'


def test_indicator_grouping_dimension_must_belong_to_indicator():
    """grouping_dimension must belong to the indicator; clean() should raise ValidationError."""

    indicator = IndicatorFactory.create()
    unrelated_dimension = DimensionFactory.create()

    indicator.grouping_dimension = unrelated_dimension
    with pytest.raises(ValidationError):
        indicator.clean()


def test_indicator_grouping_dimension_valid_when_belongs_to_indicator():
    """grouping_dimension should pass validation when it belongs to the indicator."""
    indicator = IndicatorFactory.create()
    dimension = DimensionFactory.create()
    IndicatorDimensionFactory.create(indicator=indicator, dimension=dimension)

    indicator.grouping_dimension = dimension
    indicator.clean()  # Should not raise


def test_default_visualization_union_in_schema(graphql_client_query_data):
    """IndicatorDefaultVisualization union should exist in the schema with expected members."""
    data = graphql_client_query_data(
        """
        {
          __type(name: "IndicatorDefaultVisualization") {
            kind
            possibleTypes {
              name
            }
          }
        }
        """
    )
    union_type = data['__type']
    assert union_type is not None, 'IndicatorDefaultVisualization union should exist'
    assert union_type['kind'] == 'UNION'
    type_names = {t['name'] for t in union_type['possibleTypes']}
    assert 'IndicatorDefaultBarChart' in type_names
    assert 'IndicatorDefaultLineChart' in type_names
    assert 'IndicatorDefaultAreaChart' in type_names
    assert 'IndicatorDefaultPieChart' in type_names
    assert 'IndicatorDefaultSummary' in type_names


def test_default_visualization_returns_none_when_empty(graphql_client_query_data):
    """DefaultVisualization should return None when visualization_type is empty."""
    indicator = IndicatorFactory.create(visualization_type='')
    IndicatorLevelFactory.create(indicator=indicator)
    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            defaultVisualization {
              ... on IndicatorDefaultBarChart {
                barType
              }
            }
          }
        }
        """,
        variables=dict(id=indicator.id),
    )
    assert data['indicator']['defaultVisualization'] is None


def test_default_visualization_bar_chart(graphql_client_query_data):
    """DefaultVisualization returns IndicatorDefaultBarChart with correct fields."""

    indicator = IndicatorFactory.create(
        visualization_type=VisualizationType.BAR_CHART,
        bar_type='stacked',
    )
    IndicatorLevelFactory.create(indicator=indicator)
    IndicatorValueFactory.create(indicator=indicator, value=42.0, date=datetime.date(2023, 1, 1))

    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            defaultVisualization {
              ... on IndicatorDefaultBarChart {
                barType
                indicator { id }
                chartSeries {
                  dimensionCategory { id }
                  values { value }
                }
              }
            }
          }
        }
        """,
        variables=dict(id=indicator.id),
    )
    viz = data['indicator']['defaultVisualization']
    assert viz['barType'] == 'stacked'
    assert viz['indicator']['id'] == str(indicator.id)
    assert len(viz['chartSeries']) == 1
    assert viz['chartSeries'][0]['dimensionCategory'] is None


def test_default_visualization_summary(graphql_client_query_data):
    """DefaultVisualization returns IndicatorDefaultSummary with indicator."""

    indicator = IndicatorFactory.create(visualization_type=VisualizationType.SUMMARY)
    IndicatorLevelFactory.create(indicator=indicator)

    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            defaultVisualization {
              ... on IndicatorDefaultSummary {
                indicator { id }
              }
            }
          }
        }
        """,
        variables=dict(id=indicator.id),
    )
    viz = data['indicator']['defaultVisualization']
    assert viz['indicator']['id'] == str(indicator.id)


def test_default_visualization_line_chart(graphql_client_query_data):
    """DefaultVisualization returns IndicatorDefaultLineChart with correct fields."""

    indicator = IndicatorFactory.create(
        visualization_type=VisualizationType.LINE_CHART,
        show_total_line=True,
    )
    IndicatorLevelFactory.create(indicator=indicator)
    IndicatorValueFactory.create(indicator=indicator, value=5.0, date=datetime.date(2023, 1, 1))

    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            defaultVisualization {
              ... on IndicatorDefaultLineChart {
                showTotalLine
                indicator { id }
                chartSeries {
                  dimensionCategory { id }
                  values { value }
                }
              }
            }
          }
        }
        """,
        variables=dict(id=indicator.id),
    )
    viz = data['indicator']['defaultVisualization']
    assert viz['showTotalLine'] is True
    assert viz['indicator']['id'] == str(indicator.id)
    assert len(viz['chartSeries']) == 1
    assert viz['chartSeries'][0]['dimensionCategory'] is None


def test_default_visualization_area_chart(graphql_client_query_data):
    """DefaultVisualization returns IndicatorDefaultAreaChart with correct fields."""

    indicator = IndicatorFactory.create(
        visualization_type=VisualizationType.AREA_CHART,
        show_total_line=True,
    )
    IndicatorLevelFactory.create(indicator=indicator)
    IndicatorValueFactory.create(indicator=indicator, value=7.0, date=datetime.date(2023, 1, 1))

    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            defaultVisualization {
              ... on IndicatorDefaultAreaChart {
                showTotalLine
                indicator { id }
                chartSeries {
                  dimensionCategory { id }
                  values { value }
                }
              }
            }
          }
        }
        """,
        variables=dict(id=indicator.id),
    )
    viz = data['indicator']['defaultVisualization']
    assert viz['showTotalLine'] is True
    assert viz['indicator']['id'] == str(indicator.id)
    assert len(viz['chartSeries']) == 1
    assert viz['chartSeries'][0]['dimensionCategory'] is None


def test_default_visualization_pie_chart(graphql_client_query_data):
    """DefaultVisualization returns IndicatorDefaultPieChart with correct year."""

    indicator = IndicatorFactory.create(
        visualization_type=VisualizationType.PIE_CHART,
        pie_chart_year=2023,
    )
    IndicatorLevelFactory.create(indicator=indicator)
    IndicatorValueFactory.create(indicator=indicator, value=3.0, date=datetime.date(2023, 1, 1))

    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            defaultVisualization {
              ... on IndicatorDefaultPieChart {
                year
                indicator { id }
                chartSeries {
                  dimensionCategory { id }
                  values { value }
                }
              }
            }
          }
        }
        """,
        variables=dict(id=indicator.id),
    )
    viz = data['indicator']['defaultVisualization']
    assert viz['year'] == 2023
    assert viz['indicator']['id'] == str(indicator.id)
    assert len(viz['chartSeries']) == 1


def test_bar_chart_defaults_bar_type_to_stacked_when_empty(graphql_client_query_data):
    """When bar_type is empty, the resolver should default to 'stacked'."""

    indicator = IndicatorFactory.create(
        visualization_type=VisualizationType.BAR_CHART,
        bar_type='',
    )
    IndicatorLevelFactory.create(indicator=indicator)
    IndicatorValueFactory.create(indicator=indicator, value=1.0, date=datetime.date(2023, 1, 1))

    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            defaultVisualization {
              ... on IndicatorDefaultBarChart {
                barType
              }
            }
          }
        }
        """,
        variables=dict(id=indicator.id),
    )
    viz = data['indicator']['defaultVisualization']
    assert viz['barType'] == 'stacked'


def test_default_visualization_with_grouping_dimension(graphql_client_query_data):
    """Grouping dimension produces multiple chart series with correct categories."""

    indicator = IndicatorFactory.create(
        visualization_type=VisualizationType.BAR_CHART,
        bar_type='stacked',
    )
    dimension = DimensionFactory.create(name='Sector')
    IndicatorDimensionFactory.create(indicator=indicator, dimension=dimension)
    cat_a = DimensionCategoryFactory.create(dimension=dimension, name='Transport')
    cat_b = DimensionCategoryFactory.create(dimension=dimension, name='Energy')

    indicator.grouping_dimension = dimension
    indicator.save()

    IndicatorLevelFactory.create(indicator=indicator)
    IndicatorValueFactory.create(indicator=indicator, value=10.0, date=datetime.date(2023, 1, 1), categories=[cat_a])
    IndicatorValueFactory.create(indicator=indicator, value=20.0, date=datetime.date(2023, 1, 1), categories=[cat_b])

    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            defaultVisualization {
              ... on IndicatorDefaultBarChart {
                dimension { id }
                chartSeries {
                  dimensionCategory { name }
                  values { value }
                }
              }
            }
          }
        }
        """,
        variables=dict(id=indicator.id),
    )
    viz = data['indicator']['defaultVisualization']
    assert len(viz['chartSeries']) == 2
    category_names = {s['dimensionCategory']['name'] for s in viz['chartSeries']}
    assert category_names == {'Transport', 'Energy'}
    assert viz['dimension']['id'] == str(dimension.id)


INTERFACE_TEST_CASES = [
    ('IndicatorBarChartInterface', 'INTERFACE', {'IndicatorDefaultBarChart', 'DashboardIndicatorBarChartBlock'}),
    ('IndicatorLineChartInterface', 'INTERFACE', {'IndicatorDefaultLineChart', 'DashboardIndicatorLineChartBlock'}),
    ('IndicatorAreaChartInterface', 'INTERFACE', {'IndicatorDefaultAreaChart', 'DashboardIndicatorAreaChartBlock'}),
    ('IndicatorPieChartInterface', 'INTERFACE', {'IndicatorDefaultPieChart', 'DashboardIndicatorPieChartBlock'}),
    ('IndicatorSummaryInterface', 'INTERFACE', {'IndicatorDefaultSummary', 'DashboardIndicatorSummaryBlock'}),
]


@pytest.mark.parametrize(('type_name', 'expected_kind', 'expected_implementors'), INTERFACE_TEST_CASES)
def test_indicator_chart_interfaces_exist(graphql_client_query_data, type_name, expected_kind, expected_implementors):
    """Indicator chart interfaces should exist and be implemented by IndicatorDefault* types."""
    data = graphql_client_query_data(
        """
        query($name: String!) {
          __type(name: $name) {
            kind
            possibleTypes {
              name
            }
          }
        }
        """,
        variables=dict(name=type_name),
    )
    iface = data['__type']
    assert iface is not None, f'{type_name} interface should exist'
    assert iface['kind'] == expected_kind
    actual_types = {t['name'] for t in iface['possibleTypes']}
    assert expected_implementors <= actual_types


def test_bar_chart_interface_fields_queryable(graphql_client_query_data):
    """Fields on IndicatorBarChartInterface should be queryable via fragment spread."""

    indicator = IndicatorFactory.create(
        visualization_type=VisualizationType.BAR_CHART,
        bar_type='grouped',
    )
    IndicatorLevelFactory.create(indicator=indicator)
    IndicatorValueFactory.create(indicator=indicator, value=10.0, date=datetime.date(2022, 1, 1))

    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            defaultVisualization {
              ... on IndicatorBarChartInterface {
                indicator { id }
                barType
                chartSeries {
                  dimensionCategory { id }
                  values { value }
                }
              }
            }
          }
        }
        """,
        variables=dict(id=indicator.id),
    )
    viz = data['indicator']['defaultVisualization']
    assert viz['barType'] == 'grouped'
    assert viz['indicator']['id'] == str(indicator.id)
    assert len(viz['chartSeries']) == 1
