import pytest
from datetime import date
from decimal import Decimal

from budget.tests.factories import (
    DataPointFactory, DatasetFactory, DatasetSchemaFactory, DatasetSchemaScopeFactory, DimensionFactory,
    DimensionCategoryFactory, DimensionScopeFactory
)

pytestmark = pytest.mark.django_db


def test_dimension_node(graphql_client_query_data, plan, category):
    dataset = DatasetFactory(scope=category)
    schema = dataset.schema
    dimension_category = DimensionCategoryFactory()
    schema.dimension_categories.add(dimension_category)
    dimension = dimension_category.dimension
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
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
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'datasets': [{
                'schema': {
                    'dimensionCategories': [{
                        'dimension': {
                            '__typename': 'BudgetDimension',
                            'uuid': str(dimension.uuid),
                            'name': dimension.name,
                        },
                    }],
                },
            }],
        }],
    }
    assert data == expected


def test_dimension_category_node(graphql_client_query_data, plan, category):
    dataset = DatasetFactory(scope=category)
    schema = dataset.schema
    dimension_category = DimensionCategoryFactory()
    schema.dimension_categories.add(dimension_category)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                dimensionCategories {
                  __typename
                  uuid
                  dimension {
                     __typename
                  }
                  label
                }
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'datasets': [{
                'schema': {
                    'dimensionCategories': [{
                        '__typename': 'BudgetDimensionCategory',
                        'uuid': str(dimension_category.uuid),
                        'dimension': {
                            '__typename': 'BudgetDimension',
                        },
                        'label': dimension_category.label,
                    }],
                },
            }],
        }],
    }
    assert data == expected


def test_dimension_scope_node(graphql_client_query_data, plan, category):
    scope = DimensionScopeFactory(scope=category.type)
    dimension = scope.dimension
    dimension_category = DimensionCategoryFactory(dimension=dimension)
    dataset = DatasetFactory(scope=category)
    dataset.schema.dimension_categories.add(dimension_category)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                dimensionCategories {
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
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'datasets': [{
                'schema': {
                    'dimensionCategories': [{
                        'dimension': {
                            'scopes': [{
                                '__typename': 'DimensionScope',
                                'scope': {
                                    '__typename': 'CategoryType',
                                },
                            }],
                        },
                    }],
                },
            }],
        }],
    }
    assert data == expected


def test_data_point_node(graphql_client_query_data, plan, category):
    dataset = DatasetFactory(scope=category)
    data_point = DataPointFactory(dataset=dataset, date=date(2024, 1, 1), value=10.51)
    data = graphql_client_query_data(
        '''
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
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'datasets': [{
                'dataPoints': [{
                    '__typename': 'DataPoint',
                    'uuid': str(data_point.uuid),
                    'dataset': {
                        '__typename': 'Dataset',
                    },
                    'date': data_point.date.isoformat(),
                    'value': str(Decimal(data_point.value).quantize(Decimal('0.0001'))),
                }],
            }],
        }],
    }
    assert data == expected


def test_dataset_schema_scope_node(graphql_client_query_data, plan, category):
    scope = DatasetSchemaScopeFactory(scope=category.type)
    schema = scope.schema
    dataset = DatasetFactory(scope=category, schema=schema)
    assert schema == dataset.schema
    data = graphql_client_query_data(
        '''
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
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'datasets': [{
                'schema': {
                    'scopes': [{
                        '__typename': 'DatasetSchemaScope',
                        'scope': {
                            '__typename': 'CategoryType',
                        },
                    }],
                },
            }],
        }],
    }
    assert data == expected


def test_dataset_schema_node(graphql_client_query_data, plan, category):
    dataset = DatasetFactory(scope=category)
    schema = dataset.schema
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              schema {
                __typename
                uuid
                timeResolution
                unit
                name
                scopes {
                  __typename
                }
                dimensionCategories {
                  __typename
                }
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'datasets': [{
                'schema': {
                    '__typename': 'DatasetSchema',
                    'uuid': str(schema.uuid),
                    'timeResolution': schema.time_resolution.upper(),
                    'unit': schema.unit,
                    'name': schema.name,
                    'scopes': [],
                    'dimensionCategories': [],
                },
            }],
        }],
    }
    assert data == expected


def test_dataset_node(graphql_client_query_data, plan, category):
    dataset = DatasetFactory(scope=category)
    data = graphql_client_query_data(
        '''
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
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'datasets': [{
                '__typename': 'Dataset',
                'uuid': str(dataset.uuid),
                'schema': {
                    '__typename': 'DatasetSchema',
                },
                'dataPoints': [],
            }],
        }],
    }
    assert data == expected


def test_integration_for_category(graphql_client_query_data, plan, category):
    dimension = DimensionFactory()
    dim_category1 = DimensionCategoryFactory(dimension=dimension)
    dim_category2 = DimensionCategoryFactory(dimension=dimension)

    schema = DatasetSchemaFactory()
    dataset1 = DatasetFactory(scope=category, schema=schema)
    dataset2 = DatasetFactory(scope=category, schema=schema)

    data_point1 = DataPointFactory(dataset=dataset1, date=date(2024, 1, 1), value=10.51)
    data_point1.dimension_categories.set([dim_category1])
    data_point2 = DataPointFactory(dataset=dataset1, date=date(2024, 2, 1), value=15.22)
    data_point2.dimension_categories.set([dim_category2])
    data_point3 = DataPointFactory(dataset=dataset2, date=date(2024, 3, 1), value=8)
    data_point3.dimension_categories.set([dim_category1, dim_category2])

    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            datasets {
              __typename
              uuid
              schema {
                __typename
                uuid
                timeResolution
                unit
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
        ''',
        variables={'plan': plan.identifier}
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
                            'uuid': str(schema.uuid),
                            'name': schema.name,
                            'timeResolution': schema.time_resolution.upper(),
                            'unit': schema.unit,
                        },
                        'dataPoints': [
                            {
                                '__typename': 'DataPoint',
                                'uuid': str(data_point1.uuid),
                                'date': data_point1.date.isoformat(),
                                'value': str(Decimal(data_point1.value).quantize(Decimal('0.0001'))),
                                'dimensionCategories': [
                                    {
                                        '__typename': 'BudgetDimensionCategory',
                                        'uuid': str(dim_category1.uuid),
                                        'label': dim_category1.label,
                                    },
                                ],
                            },
                            {
                                '__typename': 'DataPoint',
                                'uuid': str(data_point2.uuid),
                                'date': data_point2.date.isoformat(),
                                'value': str(Decimal(data_point2.value).quantize(Decimal('0.0001'))),
                                'dimensionCategories': [
                                    {
                                        '__typename': 'BudgetDimensionCategory',
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
                            'uuid': str(schema.uuid),
                            'name': schema.name,
                            'timeResolution': schema.time_resolution.upper(),
                            'unit': schema.unit,
                        },
                        'dataPoints': [
                            {
                                '__typename': 'DataPoint',
                                'uuid': str(data_point3.uuid),
                                'date': data_point3.date.isoformat(),
                                'value': str(Decimal(data_point3.value).quantize(Decimal('0.0001'))),
                                'dimensionCategories': [
                                    {
                                        '__typename': 'BudgetDimensionCategory',
                                        'uuid': str(dim_category1.uuid),
                                        'label': dim_category1.label,
                                    },
                                    {
                                        '__typename': 'BudgetDimensionCategory',
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
                ]
            }
        ]
    }
    assert data == expected


def test_integration_for_action(graphql_client_query_data, action):
    dimension = DimensionFactory()
    dim_category1 = DimensionCategoryFactory(dimension=dimension)
    dim_category2 = DimensionCategoryFactory(dimension=dimension)

    schema = DatasetSchemaFactory()
    dataset1 = DatasetFactory(scope=action, schema=schema)
    dataset2 = DatasetFactory(scope=action, schema=schema)

    data_point1 = DataPointFactory(dataset=dataset1, date=date(2024, 1, 1), value=10.51)
    data_point1.dimension_categories.set([dim_category1])
    data_point2 = DataPointFactory(dataset=dataset1, date=date(2024, 2, 1), value=15.22)
    data_point2.dimension_categories.set([dim_category2])
    data_point3 = DataPointFactory(dataset=dataset2, date=date(2024, 3, 1), value=8)
    data_point3.dimension_categories.set([dim_category1, dim_category2])

    data = graphql_client_query_data(
        '''
        query($actionId: ID!) {
          action(id: $actionId) {
            datasets {
              __typename
              uuid
              schema {
                __typename
                uuid
                timeResolution
                unit
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
        ''',
        variables={'actionId': action.id}
    )

    expected = {
        'action': {
            'datasets': [
                {
                    '__typename': 'Dataset',
                    'uuid': str(dataset1.uuid),
                    'schema': {
                        '__typename': 'DatasetSchema',
                        'uuid': str(schema.uuid),
                        'name': schema.name,
                        'timeResolution': schema.time_resolution.upper(),
                        'unit': schema.unit,
                    },
                    'dataPoints': [
                        {
                            '__typename': 'DataPoint',
                            'uuid': str(data_point1.uuid),
                            'date': data_point1.date.isoformat(),
                            'value': str(Decimal(data_point1.value).quantize(Decimal('0.0001'))),
                            'dimensionCategories': [
                                {
                                    '__typename': 'BudgetDimensionCategory',
                                    'uuid': str(dim_category1.uuid),
                                    'label': dim_category1.label,
                                },
                            ],
                        },
                        {
                            '__typename': 'DataPoint',
                            'uuid': str(data_point2.uuid),
                            'date': data_point2.date.isoformat(),
                            'value': str(Decimal(data_point2.value).quantize(Decimal('0.0001'))),
                            'dimensionCategories': [
                                {
                                    '__typename': 'BudgetDimensionCategory',
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
                        'uuid': str(schema.uuid),
                        'name': schema.name,
                        'timeResolution': schema.time_resolution.upper(),
                        'unit': schema.unit,
                    },
                    'dataPoints': [
                        {
                            '__typename': 'DataPoint',
                            'uuid': str(data_point3.uuid),
                            'date': data_point3.date.isoformat(),
                            'value': str(Decimal(data_point3.value).quantize(Decimal('0.0001'))),
                            'dimensionCategories': [
                                {
                                    '__typename': 'BudgetDimensionCategory',
                                    'uuid': str(dim_category1.uuid),
                                    'label': dim_category1.label,
                                },
                                {
                                    '__typename': 'BudgetDimensionCategory',
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
            ]
        }
    }

    assert data == expected
