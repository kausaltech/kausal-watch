import typing
from datetime import date

import pytest

from kausal_common.datasets.models import DatasetMetricComputation

from datasets.tests.factories import (
    DataPointFactory,
    DatasetFactory,
    DatasetMetricFactory,
    DatasetSchemaDimensionFactory,
    DatasetSchemaFactory,
    DatasetSchemaScopeFactory,
    DimensionCategoryFactory,
    DimensionFactory,
    DimensionScopeFactory,
)
from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory, IndicatorValueFactory

if typing.TYPE_CHECKING:
    from actions.models.action import Action

pytestmark = pytest.mark.django_db


def test_dimension_node(graphql_client_query_data, plan, category):
    dataset = DatasetFactory.create(scope=category)
    schema = dataset.schema
    dimension = DimensionFactory.create()
    DatasetSchemaDimensionFactory.create(schema=schema, dimension=dimension)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                dimensions {
                  dimension {
                    __typename
                    uuid
                    name
                  }
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    expected = {
        'planCategories': [
            {
                'datasets': [
                    {
                        'schema': {
                            'dimensions': [
                                {
                                    'dimension': {
                                        '__typename': 'DatasetsDimension',
                                        'uuid': str(dimension.uuid),
                                        'name': dimension.name,
                                    }
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    assert data == expected


def test_dimension_scope_node(graphql_client_query_data, plan, category):
    scope = DimensionScopeFactory.create(scope=category.type)
    dimension = scope.dimension
    dataset = DatasetFactory.create(scope=category)
    DatasetSchemaDimensionFactory.create(schema=dataset.schema, dimension=dimension)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                dimensions {
                  dimension {
                    scopes {
                      __typename
                      scope {
                        __typename
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    expected = {
        'planCategories': [
            {
                'datasets': [
                    {
                        'schema': {
                            'dimensions': [
                                {
                                    'dimension': {
                                        'scopes': [{'__typename': 'DimensionScope', 'scope': {'__typename': 'CategoryType'}}]
                                    }
                                }
                            ]
                        }
                    }
                ]
            }
        ]
    }
    assert data == expected


def test_data_point_node(graphql_client_query_data, plan, category):
    dataset = DatasetFactory.create(scope=category)
    data_point = DataPointFactory.create(dataset=dataset, date=date(2024, 1, 1), value=10.51)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              dataPoints {
                __typename
                uuid
                dataset {
                  __typename
                }
                date
                value
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    expected = {
        'planCategories': [
            {
                'datasets': [
                    {
                        'dataPoints': [
                            {
                                '__typename': 'DataPoint',
                                'uuid': str(data_point.uuid),
                                'dataset': {
                                    '__typename': 'Dataset',
                                },
                                'date': data_point.date.isoformat(),
                                'value': data_point.value,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    assert data == expected


def test_dataset_schema_scope_node(graphql_client_query_data, plan, category):
    scope = DatasetSchemaScopeFactory.create(scope=category.type)
    schema = scope.schema
    dataset = DatasetFactory.create(scope=category, schema=schema)
    assert schema == dataset.schema
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                scopes {
                  __typename
                  scope {
                    __typename
                  }
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    expected = {
        'planCategories': [
            {
                'datasets': [
                    {
                        'schema': {
                            'scopes': [
                                {
                                    '__typename': 'DatasetSchemaScope',
                                    'scope': {
                                        '__typename': 'CategoryType',
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    assert data == expected


def test_dataset_schema_node(graphql_client_query_data, plan, category):
    dataset = DatasetFactory.create(scope=category)
    schema = dataset.schema
    assert schema is not None
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                __typename
                uuid
                timeResolution
                name
                scopes {
                  __typename
                }
                dimensions {
                  __typename
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    expected = {
        'planCategories': [
            {
                'datasets': [
                    {
                        'schema': {
                            '__typename': 'DatasetSchema',
                            'uuid': str(schema.uuid),
                            'timeResolution': schema.time_resolution.upper(),
                            'name': schema.name,
                            'scopes': [],
                            'dimensions': [],
                        },
                    }
                ],
            }
        ],
    }
    assert data == expected


def test_dataset_node(graphql_client_query_data, plan, category):
    dataset = DatasetFactory(scope=category)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              __typename
              uuid
              schema {
                __typename
              }
              dataPoints {
                __typename
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    expected = {
        'planCategories': [
            {
                'datasets': [
                    {
                        '__typename': 'Dataset',
                        'uuid': str(dataset.uuid),
                        'schema': {
                            '__typename': 'DatasetSchema',
                        },
                        'dataPoints': [],
                    }
                ],
            }
        ],
    }
    assert data == expected


def test_integration_for_category(graphql_client_query_data, plan, category):
    dimension = DimensionFactory.create()
    dim_category1 = DimensionCategoryFactory.create(dimension=dimension)
    dim_category2 = DimensionCategoryFactory.create(dimension=dimension)

    schema1 = DatasetSchemaFactory.create()
    schema2 = DatasetSchemaFactory.create()
    dataset1 = DatasetFactory.create(scope=category, schema=schema1)
    dataset2 = DatasetFactory.create(scope=category, schema=schema2)

    data_point1 = DataPointFactory.create(dataset=dataset1, date=date(2024, 1, 1), value=10.51)
    data_point1.dimension_categories.set([dim_category1])
    data_point2 = DataPointFactory.create(dataset=dataset1, date=date(2024, 2, 1), value=15.22)
    data_point2.dimension_categories.set([dim_category2])
    data_point3 = DataPointFactory.create(dataset=dataset2, date=date(2024, 3, 1), value=8)
    data_point3.dimension_categories.set([dim_category1, dim_category2])

    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              __typename
              uuid
              schema {
                __typename
                uuid
                timeResolution
                name
              }
              dataPoints {
                __typename
                uuid
                date
                value
                dimensionCategories {
                  __typename
                  uuid
                  label
                }
              }
              scope {
                __typename
                ... on Category {
                  id
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )

    expected = {
        'planCategories': [
            {
                'datasets': [
                    {
                        '__typename': 'Dataset',
                        'uuid': str(dataset1.uuid),
                        'schema': {
                            '__typename': 'DatasetSchema',
                            'uuid': str(schema1.uuid),
                            'name': schema1.name,
                            'timeResolution': schema1.time_resolution.upper(),
                        },
                        'dataPoints': [
                            {
                                '__typename': 'DataPoint',
                                'uuid': str(data_point1.uuid),
                                'date': data_point1.date.isoformat(),
                                'value': data_point1.value,
                                'dimensionCategories': [
                                    {
                                        '__typename': 'DatasetsDimensionCategory',
                                        'uuid': str(dim_category1.uuid),
                                        'label': dim_category1.label,
                                    },
                                ],
                            },
                            {
                                '__typename': 'DataPoint',
                                'uuid': str(data_point2.uuid),
                                'date': data_point2.date.isoformat(),
                                'value': data_point2.value,
                                'dimensionCategories': [
                                    {
                                        '__typename': 'DatasetsDimensionCategory',
                                        'uuid': str(dim_category2.uuid),
                                        'label': dim_category2.label,
                                    },
                                ],
                            },
                        ],
                        'scope': {
                            '__typename': 'Category',
                            'id': str(category.id),
                        },
                    },
                    {
                        '__typename': 'Dataset',
                        'uuid': str(dataset2.uuid),
                        'schema': {
                            '__typename': 'DatasetSchema',
                            'uuid': str(schema2.uuid),
                            'name': schema2.name,
                            'timeResolution': schema2.time_resolution.upper(),
                        },
                        'dataPoints': [
                            {
                                '__typename': 'DataPoint',
                                'uuid': str(data_point3.uuid),
                                'date': data_point3.date.isoformat(),
                                'value': data_point3.value,
                                'dimensionCategories': [
                                    {
                                        '__typename': 'DatasetsDimensionCategory',
                                        'uuid': str(dim_category1.uuid),
                                        'label': dim_category1.label,
                                    },
                                    {
                                        '__typename': 'DatasetsDimensionCategory',
                                        'uuid': str(dim_category2.uuid),
                                        'label': dim_category2.label,
                                    },
                                ],
                            },
                        ],
                        'scope': {
                            '__typename': 'Category',
                            'id': str(category.id),
                        },
                    },
                ],
            },
        ],
    }
    assert data == expected


def test_integration_for_action(graphql_client_query_data, action: Action):
    dimension = DimensionFactory.create()
    dim_category1 = DimensionCategoryFactory.create(dimension=dimension)
    dim_category2 = DimensionCategoryFactory.create(dimension=dimension)

    schema1 = DatasetSchemaFactory.create()
    schema2 = DatasetSchemaFactory.create()
    dataset1 = DatasetFactory.create(scope=action, schema=schema1)
    dataset2 = DatasetFactory.create(scope=action, schema=schema2)

    data_point2 = DataPointFactory.create(dataset=dataset1, date=date(2024, 2, 1), value=15.22)
    data_point2.dimension_categories.set([dim_category2])
    data_point1 = DataPointFactory.create(dataset=dataset1, date=date(2024, 1, 1), value=10.51)
    data_point1.dimension_categories.set([dim_category1])
    data_point3 = DataPointFactory.create(dataset=dataset2, date=date(2024, 3, 1), value=8.0)
    data_point3.dimension_categories.set([dim_category1, dim_category2])

    data = graphql_client_query_data(
        """
        query($actionId: ID!) {
          action(id: $actionId) {
            datasets {
              __typename
              uuid
              schema {
                __typename
                uuid
                timeResolution
                name
              }
              dataPoints {
                __typename
                uuid
                date
                value
                dimensionCategories {
                  __typename
                  uuid
                  label
                }
              }
              scope {
                __typename
                ... on Action {
                  id
                }
              }
            }
          }
        }
        """,
        variables={'actionId': action.id},
    )

    expected = {
        'action': {
            'datasets': [
                {
                    '__typename': 'Dataset',
                    'uuid': str(dataset1.uuid),
                    'schema': {
                        '__typename': 'DatasetSchema',
                        'uuid': str(schema1.uuid),
                        'name': schema1.name,
                        'timeResolution': schema1.time_resolution.upper(),
                    },
                    'dataPoints': [
                        {
                            '__typename': 'DataPoint',
                            'uuid': str(data_point1.uuid),
                            'date': data_point1.date.isoformat(),
                            'value': data_point1.value,
                            'dimensionCategories': [
                                {
                                    '__typename': 'DatasetsDimensionCategory',
                                    'uuid': str(dim_category1.uuid),
                                    'label': dim_category1.label,
                                },
                            ],
                        },
                        {
                            '__typename': 'DataPoint',
                            'uuid': str(data_point2.uuid),
                            'date': data_point2.date.isoformat(),
                            'value': data_point2.value,
                            'dimensionCategories': [
                                {
                                    '__typename': 'DatasetsDimensionCategory',
                                    'uuid': str(dim_category2.uuid),
                                    'label': dim_category2.label,
                                },
                            ],
                        },
                    ],
                    'scope': {
                        '__typename': 'Action',
                        'id': str(action.id),
                    },
                },
                {
                    '__typename': 'Dataset',
                    'uuid': str(dataset2.uuid),
                    'schema': {
                        '__typename': 'DatasetSchema',
                        'uuid': str(schema2.uuid),
                        'name': schema2.name,
                        'timeResolution': schema2.time_resolution.upper(),
                    },
                    'dataPoints': [
                        {
                            '__typename': 'DataPoint',
                            'uuid': str(data_point3.uuid),
                            'date': data_point3.date.isoformat(),
                            'value': data_point3.value,
                            'dimensionCategories': [
                                {
                                    '__typename': 'DatasetsDimensionCategory',
                                    'uuid': str(dim_category1.uuid),
                                    'label': dim_category1.label,
                                },
                                {
                                    '__typename': 'DatasetsDimensionCategory',
                                    'uuid': str(dim_category2.uuid),
                                    'label': dim_category2.label,
                                },
                            ],
                        },
                    ],
                    'scope': {
                        '__typename': 'Action',
                        'id': str(action.id),
                    },
                },
            ],
        },
    }

    assert data == expected


def test_dataset_metric_node(graphql_client_query_data, plan, category):
    schema = DatasetSchemaFactory.create()
    metric = DatasetMetricFactory.create(schema=schema, label='CO2 emissions', name='co2', unit='t')
    DatasetFactory.create(scope=category, schema=schema)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                metrics {
                  __typename
                  uuid
                  name
                  label
                  unit
                  order
                  schema {
                    __typename
                    uuid
                  }
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    expected = {
        'planCategories': [
            {
                'datasets': [
                    {
                        'schema': {
                            'metrics': [
                                {
                                    '__typename': 'DatasetMetricNode',
                                    'uuid': str(metric.uuid),
                                    'name': metric.name,
                                    'label': metric.label,
                                    'unit': metric.unit,
                                    'order': metric.order,
                                    'schema': {
                                        '__typename': 'DatasetSchema',
                                        'uuid': str(schema.uuid),
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    assert data == expected


def test_metric_is_computed(graphql_client_query_data, plan, category):
    schema = DatasetSchemaFactory.create()
    metric_a = DatasetMetricFactory.create(schema=schema, label='Input A')
    metric_b = DatasetMetricFactory.create(schema=schema, label='Input B')
    metric_c = DatasetMetricFactory.create(schema=schema, label='Computed')
    DatasetMetricComputation.objects.create(
        schema=schema,
        target_metric=metric_c,
        operation='add',
        operand_a=metric_a,
        operand_b=metric_b,
    )
    DatasetFactory.create(scope=category, schema=schema)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                metrics {
                  label
                  isComputed
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    metrics = data['planCategories'][0]['datasets'][0]['schema']['metrics']
    by_label = {m['label']: m['isComputed'] for m in metrics}
    assert by_label['Input A'] is False
    assert by_label['Input B'] is False
    assert by_label['Computed'] is True


def test_dimension_node_categories(graphql_client_query_data, plan, category):
    dimension = DimensionFactory.create()
    dim_category = DimensionCategoryFactory.create(dimension=dimension)
    schema = DatasetSchemaFactory.create()
    DatasetSchemaDimensionFactory.create(schema=schema, dimension=dimension)
    DatasetFactory.create(scope=category, schema=schema)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                dimensions {
                  dimension {
                    categories {
                      __typename
                      uuid
                      label
                    }
                  }
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    expected = {
        'planCategories': [
            {
                'datasets': [
                    {
                        'schema': {
                            'dimensions': [
                                {
                                    'dimension': {
                                        'categories': [
                                            {
                                                '__typename': 'DatasetsDimensionCategory',
                                                'uuid': str(dim_category.uuid),
                                                'label': dim_category.label,
                                            }
                                        ],
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    assert data == expected


def test_dimension_category_dimension_field(graphql_client_query_data, plan, category):
    from datetime import date as date_type

    dimension = DimensionFactory.create()
    dim_category = DimensionCategoryFactory.create(dimension=dimension)
    schema = DatasetSchemaFactory.create()
    DatasetSchemaDimensionFactory.create(schema=schema, dimension=dimension)
    dataset = DatasetFactory.create(scope=category, schema=schema)
    dp = DataPointFactory.create(dataset=dataset, date=date_type(2024, 6, 1), value=1.0)
    dp.dimension_categories.set([dim_category])
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              dataPoints {
                dimensionCategories {
                  dimension {
                    __typename
                    uuid
                    name
                  }
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    dim_result = data['planCategories'][0]['datasets'][0]['dataPoints'][0]['dimensionCategories'][0]['dimension']
    assert dim_result == {
        '__typename': 'DatasetsDimension',
        'uuid': str(dimension.uuid),
        'name': dimension.name,
    }


def test_computed_data_points(graphql_client_query_data, plan, category):
    schema = DatasetSchemaFactory.create()
    metric_a = DatasetMetricFactory.create(schema=schema, label='A')
    metric_b = DatasetMetricFactory.create(schema=schema, label='B')
    metric_c = DatasetMetricFactory.create(schema=schema, label='C')
    DatasetMetricComputation.objects.create(
        schema=schema,
        target_metric=metric_c,
        operation='multiply',
        operand_a=metric_a,
        operand_b=metric_b,
    )
    dataset = DatasetFactory.create(scope=category, schema=schema)
    DataPointFactory.create(dataset=dataset, metric=metric_a, date=date(2024, 1, 1), value=3.0)
    DataPointFactory.create(dataset=dataset, metric=metric_b, date=date(2024, 1, 1), value=5.0)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              computedDataPoints {
                date
                value
                metric {
                  label
                }
                dimensionCategories {
                  uuid
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    computed = data['planCategories'][0]['datasets'][0]['computedDataPoints']
    assert len(computed) == 1
    assert computed[0]['date'] == '2024-01-01'
    assert computed[0]['value'] == 15.0
    assert computed[0]['metric']['label'] == 'C'
    assert computed[0]['dimensionCategories'] == []


def test_dataset_schema_dimension_order_and_schema(graphql_client_query_data, plan, category):
    schema = DatasetSchemaFactory.create()
    dimension = DimensionFactory.create()
    schema_dim = DatasetSchemaDimensionFactory.create(schema=schema, dimension=dimension)
    DatasetFactory.create(scope=category, schema=schema)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                dimensions {
                  __typename
                  order
                  schema {
                    __typename
                    uuid
                  }
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    expected = {
        'planCategories': [
            {
                'datasets': [
                    {
                        'schema': {
                            'dimensions': [
                                {
                                    '__typename': 'DatasetSchemaDimension',
                                    'order': schema_dim.order,
                                    'schema': {
                                        '__typename': 'DatasetSchema',
                                        'uuid': str(schema.uuid),
                                    },
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    assert data == expected


def test_computed_data_points_empty(graphql_client_query_data, plan, category):
    dataset = DatasetFactory.create(scope=category)
    DataPointFactory.create(dataset=dataset, date=date(2024, 1, 1), value=10.0)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              computedDataPoints {
                date
                value
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    computed = data['planCategories'][0]['datasets'][0]['computedDataPoints']
    assert computed == []


def test_dimension_scope_plan_type(graphql_client_query_data, plan, category):
    scope = DimensionScopeFactory.create(scope=plan)
    dimension = scope.dimension
    schema = DatasetSchemaFactory.create()
    DatasetSchemaDimensionFactory.create(schema=schema, dimension=dimension)
    DatasetFactory.create(scope=category, schema=schema)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                dimensions {
                  dimension {
                    scopes {
                      scope {
                        __typename
                        ... on Plan {
                          id
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    scopes = data['planCategories'][0]['datasets'][0]['schema']['dimensions'][0]['dimension']['scopes']
    assert scopes == [{'scope': {'__typename': 'Plan', 'id': plan.identifier}}]


def test_dataset_schema_scope_plan_type(graphql_client_query_data, plan, category):
    scope = DatasetSchemaScopeFactory.create(scope=plan)
    schema = scope.schema
    DatasetFactory.create(scope=category, schema=schema)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                scopes {
                  scope {
                    __typename
                    ... on Plan {
                      id
                    }
                  }
                }
              }
            }
          }
        }
        """,
        variables={'plan': plan.identifier},
    )
    scopes = data['planCategories'][0]['datasets'][0]['schema']['scopes']
    assert scopes == [{'scope': {'__typename': 'Plan', 'id': plan.identifier}}]


class TestIndicatorDatasets:
    """Tests for querying datasets and computed data points through the indicator GraphQL type."""

    @pytest.fixture(autouse=True)
    def _enable_indicator_factors(self, plan, plan_features):
        plan_features.enable_indicator_factors = True
        plan_features.save(update_fields=['enable_indicator_factors'])

    def test_datasets_hidden_when_feature_disabled(self, graphql_client_query_data, plan):
        plan.features.enable_indicator_factors = False
        plan.features.save(update_fields=['enable_indicator_factors'])
        indicator = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        schema = DatasetSchemaFactory.create()
        DatasetFactory.create(scope=indicator, schema=schema)
        data = graphql_client_query_data(
            """
            query($plan: ID!) {
              planIndicators(plan: $plan) {
                datasets {
                  uuid
                }
              }
            }
            """,
            variables={'plan': plan.identifier},
        )
        assert data['planIndicators'][0]['datasets'] == []

    def test_indicator_dataset_node(self, graphql_client_query_data, plan):
        indicator = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        schema = DatasetSchemaFactory.create()
        dataset = DatasetFactory.create(scope=indicator, schema=schema)
        data = graphql_client_query_data(
            """
            query($plan: ID!) {
              planIndicators(plan: $plan) {
                datasets {
                  __typename
                  uuid
                  schema {
                    __typename
                    uuid
                  }
                }
              }
            }
            """,
            variables={'plan': plan.identifier},
        )
        indicators = data['planIndicators']
        assert len(indicators) == 1
        datasets = indicators[0]['datasets']
        assert len(datasets) == 1
        assert datasets[0]['__typename'] == 'Dataset'
        assert datasets[0]['uuid'] == str(dataset.uuid)
        assert datasets[0]['schema']['uuid'] == str(schema.uuid)

    def test_indicator_computed_data_points_with_null_operand(self, graphql_client_query_data, plan):
        """Null operand_a computation resolves indicator values as virtual input."""
        indicator = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        IndicatorValueFactory.create(indicator=indicator, date=date(2024, 1, 1), value=100.0)

        schema = DatasetSchemaFactory.create()
        factor = DatasetMetricFactory.create(schema=schema, label='Emission factor', unit='tCO2e/vehicle')
        target = DatasetMetricFactory.create(schema=schema, label='Total emissions', unit='tCO2e')
        DatasetMetricComputation.objects.create(
            schema=schema,
            target_metric=target,
            operation='multiply',
            operand_a=None,
            operand_b=factor,
        )
        dataset = DatasetFactory.create(scope=indicator, schema=schema)
        DataPointFactory.create(dataset=dataset, metric=factor, date=date(2024, 1, 1), value=0.5)

        data = graphql_client_query_data(
            """
            query($plan: ID!) {
              planIndicators(plan: $plan) {
                datasets {
                  computedDataPoints {
                    date
                    value
                    metric {
                      label
                    }
                    dimensionCategories {
                      uuid
                    }
                  }
                }
              }
            }
            """,
            variables={'plan': plan.identifier},
        )
        indicators = data['planIndicators']
        assert len(indicators) == 1
        computed = indicators[0]['datasets'][0]['computedDataPoints']
        assert len(computed) == 1
        assert computed[0]['date'] == '2024-01-01'
        assert computed[0]['value'] == 50.0
        assert computed[0]['metric']['label'] == 'Total emissions'
        assert computed[0]['dimensionCategories'] == []

    def test_indicator_null_operand_multiple_dates(self, graphql_client_query_data, plan):
        """Null operand_a computation works across multiple dates."""
        indicator = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        IndicatorValueFactory.create(indicator=indicator, date=date(2024, 1, 1), value=100.0)
        IndicatorValueFactory.create(indicator=indicator, date=date(2025, 1, 1), value=200.0)

        schema = DatasetSchemaFactory.create()
        factor = DatasetMetricFactory.create(schema=schema, label='Factor')
        target = DatasetMetricFactory.create(schema=schema, label='Result')
        DatasetMetricComputation.objects.create(
            schema=schema,
            target_metric=target,
            operation='multiply',
            operand_a=None,
            operand_b=factor,
        )
        dataset = DatasetFactory.create(scope=indicator, schema=schema)
        DataPointFactory.create(dataset=dataset, metric=factor, date=date(2024, 1, 1), value=0.5)
        DataPointFactory.create(dataset=dataset, metric=factor, date=date(2025, 1, 1), value=0.3)

        data = graphql_client_query_data(
            """
            query($plan: ID!) {
              planIndicators(plan: $plan) {
                datasets {
                  computedDataPoints {
                    date
                    value
                    metric {
                      label
                    }
                  }
                }
              }
            }
            """,
            variables={'plan': plan.identifier},
        )
        computed = data['planIndicators'][0]['datasets'][0]['computedDataPoints']
        assert len(computed) == 2
        by_date = {c['date']: c for c in computed}
        assert by_date['2024-01-01']['value'] == 50.0
        assert by_date['2025-01-01']['value'] == 60.0

    def test_indicator_null_operand_no_factor_data(self, graphql_client_query_data, plan):
        """No computed data points when factor has no data for the date."""
        indicator = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        IndicatorValueFactory.create(indicator=indicator, date=date(2024, 1, 1), value=100.0)

        schema = DatasetSchemaFactory.create()
        factor = DatasetMetricFactory.create(schema=schema, label='Factor')
        target = DatasetMetricFactory.create(schema=schema, label='Result')
        DatasetMetricComputation.objects.create(
            schema=schema,
            target_metric=target,
            operation='multiply',
            operand_a=None,
            operand_b=factor,
        )
        DatasetFactory.create(scope=indicator, schema=schema)
        # No DataPoint for factor — should produce no results

        data = graphql_client_query_data(
            """
            query($plan: ID!) {
              planIndicators(plan: $plan) {
                datasets {
                  computedDataPoints {
                    date
                    value
                  }
                }
              }
            }
            """,
            variables={'plan': plan.identifier},
        )
        computed = data['planIndicators'][0]['datasets'][0]['computedDataPoints']
        assert computed == []

    def test_indicator_null_operand_no_indicator_values(self, graphql_client_query_data, plan):
        """No computed data points when indicator has no values."""
        indicator = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        # No IndicatorValue created

        schema = DatasetSchemaFactory.create()
        factor = DatasetMetricFactory.create(schema=schema, label='Factor')
        target = DatasetMetricFactory.create(schema=schema, label='Result')
        DatasetMetricComputation.objects.create(
            schema=schema,
            target_metric=target,
            operation='multiply',
            operand_a=None,
            operand_b=factor,
        )
        dataset = DatasetFactory.create(scope=indicator, schema=schema)
        DataPointFactory.create(dataset=dataset, metric=factor, date=date(2024, 1, 1), value=0.5)

        data = graphql_client_query_data(
            """
            query($plan: ID!) {
              planIndicators(plan: $plan) {
                datasets {
                  computedDataPoints {
                    date
                    value
                  }
                }
              }
            }
            """,
            variables={'plan': plan.identifier},
        )
        computed = data['planIndicators'][0]['datasets'][0]['computedDataPoints']
        assert computed == []
