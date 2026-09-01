from __future__ import annotations

from datetime import date

import pytest

from paths_integration.__generated__.graphql_client.node_values import (
    NodeValuesNode,
    NodeValuesNodeMetricDim,
    NodeValuesNodeMetricDimUnit,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def node_values_node():
    unit = NodeValuesNodeMetricDimUnit(short='%')

    metric_dim = NodeValuesNodeMetricDim(  # pyright: ignore[reportCallIssue]
        id='test_data',
        unit=unit,
        dimensions=[],
        years=list(range(2010, 2041)),
        values=[
            0.1,
            0.2,
            0.3,
            0.4,
            0.5,
            0.6,
            0.7,
            0.8,
            0.9,
            0.10,
            0.11,
            0.12,
            8,
            16,
            24,
            32,
            40,
            48,
            56,
            64,
            72,
            80,
            88,
            96,
            100,
            100,
            100,
            100,
            100,
            100,
            100,
        ],
        forecast_from=2024,  # pyright: ignore[reportCallIssue]
    )

    node = NodeValuesNode(typename__='Node', id='test_data', name='Test node name', metric_dim=metric_dim)  # pyright: ignore[reportCallIssue]

    return node


def test_set_values_from_import(node_values_node, indicator):
    metric_dim = node_values_node.metric_dim
    import_parameters = {
        'node': node_values_node.id,
        'instance': 'test-instance',
        'source_url': 'https://test.example.com/node/test_data',
        'forecast_from': metric_dim.forecast_from,
    }
    max_year = 2023

    indicator.set_values_from_import(metric_dim, import_parameters, max_year=max_year)

    indicator_values = indicator.values.filter(date__year__lte=max_year).order_by('date')
    assert indicator_values.count() == 14

    first_value = indicator_values.first()
    assert first_value.date == date(2010, 12, 31)
    assert first_value.value == 0.1

    last_value = indicator_values.last()
    assert last_value.date == date(2023, 12, 31)
    assert last_value.value == 16

    future_values = indicator.values.filter(date__year__gt=max_year)
    assert future_values.count() == 0

    import_logs = indicator.values_import_logs.all()
    assert import_logs.count() == 1
    import_log = import_logs.first()
    assert import_log.source_system == 'kausal_paths'
    assert import_log.source_url == import_parameters['source_url']
    assert import_log.import_parameters == import_parameters


def test_set_values_from_import_updates_existing_values(node_values_node, indicator, indicator_value_factory):
    existing_value = indicator_value_factory(indicator=indicator, date=date(2015, 12, 31), value=999.0)

    metric_dim = node_values_node.metric_dim
    import_parameters = {
        'node': node_values_node.id,
        'instance': 'test-instance',
        'source_url': 'https://test.example.com/node/test_data',
        'forecast_from': metric_dim.forecast_from,
    }
    max_year = 2023

    indicator.set_values_from_import(metric_dim, import_parameters, max_year=max_year)

    value_2015 = indicator.values.get(date__year=2015)
    assert value_2015.value == 0.6
    assert value_2015.id == existing_value.id


def test_set_values_from_import_removes_values_not_in_import(node_values_node, indicator, indicator_value_factory):
    indicator_value_factory(indicator=indicator, date=date(2005, 12, 31), value=123.0)

    metric_dim = node_values_node.metric_dim
    import_parameters = {
        'node': node_values_node.id,
        'instance': 'test-instance',
        'source_url': 'https://test.example.com/node/test_data',
        'forecast_from': metric_dim.forecast_from,
    }
    max_year = 2023

    indicator.set_values_from_import(metric_dim, import_parameters, max_year=max_year)

    assert not indicator.values.filter(date__year=2005).exists()
