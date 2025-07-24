from datetime import date

import pytest

from actions.models.action import Action
from datasets.tests.factories import (
    DataPointFactory,
    DatasetFactory,
    DatasetSchemaDimensionFactory,
    DatasetSchemaFactory,
    DatasetSchemaScopeFactory,
    DimensionCategoryFactory,
    DimensionFactory,
    DimensionScopeFactory,
)

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
        'planCategories': [{
            'datasets': [{
                'schema': {
                    'dimensions': [{
                        'dimension': {
                            '__typename': 'DatasetsDimension',
                            'uuid': str(dimension.uuid),
                            'name': dimension.name,
                        }
                    }],
                },
            }],
        }],
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
        'planCategories': [{
            'datasets': [{
                'schema': {
                    'dimensions': [{
                        'dimension': {
                            'scopes': [{
                                '__typename': 'DimensionScope',
                                'scope': {
                                    '__typename': 'CategoryType'
                                }
                            }]
                        }
                    }]
                }
            }]
        }]
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
        'planCategories': [{
            'datasets': [{
                'dataPoints': [{
                    '__typename': 'DataPoint',
                    'uuid': str(data_point.uuid),
                    'dataset': {
                        '__typename': 'Dataset',
                    },
                    'date': data_point.date.isoformat(),
                    'value': data_point.value,
                }],
            }],
        }],
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
        'planCategories': [{
            'datasets': [{
                'schema': {
                    '__typename': 'DatasetSchema',
                    'uuid': str(schema.uuid),
                    'timeResolution': schema.time_resolution.upper(),
                    'name': schema.name,
                    'scopes': [],
                    'dimensions': [],
                },
            }],
        }],
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
