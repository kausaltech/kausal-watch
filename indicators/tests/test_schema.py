import json
import pytest

from actions.tests.factories import ActionFactory, CategoryFactory, PlanFactory
from indicators.tests.factories import (
    ActionIndicatorFactory, CommonIndicatorFactory, DimensionCategoryFactory, DimensionFactory, IndicatorFactory,
    IndicatorDimensionFactory, IndicatorGoalFactory, IndicatorGraphFactory, IndicatorLevelFactory,
    IndicatorValueFactory, QuantityFactory, RelatedIndicatorFactory, UnitFactory
)

pytestmark = pytest.mark.django_db


def test_unit_node(graphql_client_query_data):
    unit = UnitFactory()
    indicator = IndicatorFactory(unit=unit)
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            unit {
              __typename
              id
              name
              shortName
              verboseName
              verboseNamePlural
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            'unit': {
                '__typename': 'Unit',
                'id': str(unit.id),
                'name': unit.name,
                'shortName': unit.short_name,
                'verboseName': unit.verbose_name,
                'verboseNamePlural': unit.verbose_name_plural,
            }
        }
    }
    assert data == expected


def test_quantity_node(graphql_client_query_data):
    quantity = QuantityFactory()
    indicator = IndicatorFactory(quantity=quantity)
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            quantity {
              __typename
              id
              name
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            'quantity': {
                '__typename': 'Quantity',
                'id': str(quantity.id),
                'name': quantity.name,
            }
        }
    }
    assert data == expected


def test_related_indicator_node(graphql_client_query_data):
    related_indicator = RelatedIndicatorFactory()
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            relatedEffects {
              __typename
              id
              causalIndicator {
                __typename
                id
              }
              effectIndicator {
                __typename
                id
              }
              effectType
              confidenceLevel
            }
          }
        }
        ''',
        variables=dict(indicator=related_indicator.causal_indicator.id)
    )
    expected = {
        'indicator': {
            'relatedEffects': [{
                '__typename': 'RelatedIndicator',
                'id': str(related_indicator.id),
                'causalIndicator': {
                    '__typename': 'Indicator',
                    'id': str(related_indicator.causal_indicator.id),
                },
                'effectIndicator': {
                    '__typename': 'Indicator',
                    'id': str(related_indicator.effect_indicator.id),
                },
                'effectType': related_indicator.effect_type.upper(),
                'confidenceLevel': related_indicator.confidence_level.upper(),
            }]
        }
    }
    assert data == expected


def test_action_indicator_node(graphql_client_query_data):
    indicator = IndicatorFactory()
    action_indicator = ActionIndicatorFactory(indicator=indicator)
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            relatedActions {
              __typename
              id
              action {
                __typename
                id
              }
              indicator {
                __typename
                id
              }
              effectType
              indicatesActionProgress
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            'relatedActions': [{
                '__typename': 'ActionIndicator',
                'id': str(action_indicator.id),
                'action': {
                    '__typename': 'Action',
                    'id': str(action_indicator.action.id),
                },
                'indicator': {
                    '__typename': 'Indicator',
                    'id': str(action_indicator.indicator.id),
                },
                'effectType': action_indicator.effect_type.upper(),
                'indicatesActionProgress': action_indicator.indicates_action_progress,
            }]
        }
    }
    assert data == expected


def test_indicator_graph_node(graphql_client_query_data):
    indicator = IndicatorFactory()
    indicator_graph = IndicatorGraphFactory(indicator=indicator)
    indicator.latest_graph = indicator_graph
    indicator.save(update_fields=['latest_graph'])
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            latestGraph {
              __typename
              id
              indicator {
                __typename
                id
              }
              data
              createdAt
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            'latestGraph': {
                '__typename': 'IndicatorGraph',
                'id': str(indicator_graph.id),
                'indicator': {
                    '__typename': 'Indicator',
                    'id': str(indicator.id),
                },
                'data': json.dumps(indicator_graph.data),
                'createdAt': indicator_graph.created_at.isoformat(),
            }
        }
    }
    assert data == expected


def test_indicator_level_node(graphql_client_query_data):
    plan = PlanFactory()
    indicator_level = IndicatorLevelFactory(plan=plan)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            indicatorLevels {
              __typename
              id
              indicator {
                __typename
                id
              }
              plan {
                __typename
                id
              }
              level
            }
          }
        }
        ''',
        variables=dict(plan=plan.identifier)
    )
    expected = {
        'plan': {
            'indicatorLevels': [{
                '__typename': 'IndicatorLevel',
                'id': str(indicator_level.id),
                'indicator': {
                    '__typename': 'Indicator',
                    'id': str(indicator_level.indicator.id),
                },
                'plan': {
                    '__typename': 'Plan',
                    'id': str(plan.identifier),
                },
                'level': indicator_level.level.upper(),
            }]
        }
    }
    assert data == expected


def test_dimension_node(graphql_client_query_data):
    indicator = IndicatorFactory()
    dimension = DimensionFactory()
    IndicatorDimensionFactory(indicator=indicator, dimension=dimension)
    dimension_category = DimensionCategoryFactory(dimension=dimension)
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            dimensions {
              dimension {
                __typename
                id
                name
                categories {
                  __typename
                  id
                }
              }
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            'dimensions': [{
                'dimension': {
                    '__typename': 'Dimension',
                    'id': str(dimension.id),
                    'name': dimension.name,
                    'categories': [{
                        '__typename': 'DimensionCategory',
                        'id': str(dimension_category.id),
                    }],
                }
            }]
        }
    }
    assert data == expected


def test_dimension_category_node(graphql_client_query_data):
    indicator = IndicatorFactory()
    dimension = DimensionFactory()
    IndicatorDimensionFactory(indicator=indicator, dimension=dimension)
    dimension_category = DimensionCategoryFactory(dimension=dimension)
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            dimensions {
              dimension {
                id  # Necessary to work around a presumed bug in graphene-django-optimizer
                categories {
                  __typename
                  id
                  dimension {
                    __typename
                    id
                  }
                  name
                  order
                }
              }
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            'dimensions': [{
                'dimension': {
                    'id': str(dimension.id),
                    'categories': [{
                        '__typename': 'DimensionCategory',
                        'id': str(dimension_category.id),
                        'dimension': {
                            '__typename': 'Dimension',
                            'id': str(dimension.id),
                        },
                        'name': dimension_category.name,
                        'order': 1,
                    }]
                }
            }]
        }
    }
    assert data == expected


def test_framework_node(graphql_client_query_data):
    # FIXME: FrameworkNode does not appear in a schema
    pass


def test_common_indicator_node(graphql_client_query_data):
    common_indicator = CommonIndicatorFactory()
    indicator = IndicatorFactory(common=common_indicator)
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            common {
              __typename
              id
              identifier
              name
              description
              quantity {
                __typename
                id
              }
              unit {
                __typename
                id
              }
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            'common': {
                '__typename': 'CommonIndicator',
                'id': str(common_indicator.id),
                'identifier': common_indicator.identifier,
                'name': common_indicator.name,
                'description': str(common_indicator.description),
                'quantity': {
                    '__typename': 'Quantity',
                    'id': str(common_indicator.quantity.id),
                },
                'unit': {
                    '__typename': 'Unit',
                    'id': str(common_indicator.unit.id),
                },
            }
        }
    }
    assert data == expected


def test_framework_indicator_node(graphql_client_query):
    # FIXME: FrameworkIndicatorNode does not appear in a schema
    pass


def test_indicator_value_node(graphql_client_query_data):
    category = DimensionCategoryFactory()
    indicator = IndicatorFactory()
    indicator_value = IndicatorValueFactory(indicator=indicator, categories=[category])
    indicator.latest_value = indicator_value
    indicator.save(update_fields=['latest_value'])
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            latestValue {
              __typename
              id
              indicator {
                __typename
                id
              }
              value
              date
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            'latestValue': {
                '__typename': 'IndicatorValue',
                'id': str(indicator_value.id),
                'indicator': {
                    '__typename': 'Indicator',
                    'id': str(indicator.id),
                },
                'value': indicator_value.value,
                'date': indicator_value.date.isoformat(),
            }
        }
    }
    assert data == expected


def test_indicator_goal_node(graphql_client_query_data):
    indicator = IndicatorFactory()
    indicator_goal = IndicatorGoalFactory(indicator=indicator)
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            goals {
              __typename
              id
              indicator {
                __typename
                id
              }
              scenario {
                __typename
                id
              }
              value
              date
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            'goals': [{
                '__typename': 'IndicatorGoal',
                'id': str(indicator_goal.id),
                'indicator': {
                    '__typename': 'Indicator',
                    'id': str(indicator.id),
                },
                'scenario': None,
                'value': indicator_goal.value,
                'date': indicator_goal.date.isoformat(),
            }]
        }
    }
    assert data == expected


def test_indicator_node(graphql_client_query_data):
    plan = PlanFactory()
    indicator = IndicatorFactory()
    indicator_goal = IndicatorGoalFactory(indicator=indicator)
    indicator_value = IndicatorValueFactory(indicator=indicator)
    indicator_graph = IndicatorGraphFactory(indicator=indicator)
    indicator.latest_value = indicator_value
    indicator.latest_graph = indicator_graph
    indicator.save(update_fields=['latest_value', 'latest_graph'])
    action = ActionFactory(plan=plan)
    action_indicator = ActionIndicatorFactory(action=action, indicator=indicator)
    category = CategoryFactory()
    indicator.categories.add(category)
    indicator_dimension = IndicatorDimensionFactory(indicator=indicator)
    # Create IndicatorLevel so that `plan` appears in `indicator.plan`
    IndicatorLevelFactory(indicator=indicator, plan=plan)
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            __typename
            id
            common {
              __typename
              id
            }
            organization {
              __typename
              id
            }
            identifier
            name
            quantity {
              __typename
              id
            }
            unit {
              __typename
              id
            }
            description
            minValue
            maxValue
            categories {
              __typename
              id
            }
            timeResolution
            reference
            latestValue {
              __typename
              id
            }
            latestGraph {
              __typename
              id
            }
            updatedAt
            createdAt
            values {
              __typename
              id
            }
            plans {
              __typename
              id
            }
            goals {
              __typename
              id
            }
            relatedActions {
              __typename
              id
            }
            actions {
              __typename
              id
            }
            # The following are in a separate test case
            # relatedCauses {
            #   __typename
            #   id
            # }
            # relatedEffects {
            #   __typename
            #   id
            # }
            dimensions {
              __typename
              id
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            '__typename': 'Indicator',
            'id': str(indicator.id),
            'common': {
                '__typename': 'CommonIndicator',
                'id': str(indicator.common.id),
            },
            'organization': {
                '__typename': 'Organization',
                'id': str(indicator.organization.id),
            },
            'identifier': indicator.identifier,
            'name': indicator.name,
            'quantity': {
                '__typename': 'Quantity',
                'id': str(indicator.quantity.id),
            },
            'unit': {
                '__typename': 'Unit',
                'id': str(indicator.unit.id),
            },
            'description': indicator.description,
            'minValue': indicator.min_value,
            'maxValue': indicator.max_value,
            'categories': [{
                '__typename': 'Category',
                'id': str(category.id),
            }],
            'timeResolution': indicator.time_resolution.upper(),
            'reference': indicator.reference,
            'latestValue': {
                '__typename': 'IndicatorValue',
                'id': str(indicator.latest_value.id),
            },
            'latestGraph': {
                '__typename': 'IndicatorGraph',
                'id': str(indicator.latest_graph.id),
            },
            'updatedAt': indicator.updated_at.isoformat(),
            'createdAt': indicator.created_at.isoformat(),
            'values': [{
                '__typename': 'IndicatorValue',
                'id': str(indicator.latest_value.id),
            }],
            'plans': [{
                '__typename': 'Plan',
                'id': str(plan.identifier),
            }],
            'goals': [{
                '__typename': 'IndicatorGoal',
                'id': str(indicator_goal.id),
            }],
            'relatedActions': [{
                '__typename': 'ActionIndicator',
                'id': str(action_indicator.id),
            }],
            'actions': [{
                '__typename': 'Action',
                'id': str(action.id),
            }],
            'dimensions': [{
                '__typename': 'IndicatorDimension',
                'id': str(indicator_dimension.id),
            }],
        }
    }
    assert data == expected


def test_indicator_node_cause_effect(graphql_client_query_data):
    indicator = IndicatorFactory()
    cause = RelatedIndicatorFactory(effect_indicator=indicator)
    effect = RelatedIndicatorFactory(causal_indicator=indicator)
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            __typename
            id
            relatedCauses {
              __typename
              id
            }
            relatedEffects {
              __typename
              id
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            '__typename': 'Indicator',
            'id': str(indicator.id),
            'relatedCauses': [{
                '__typename': 'RelatedIndicator',
                'id': str(cause.id),
            }],
            'relatedEffects': [{
                '__typename': 'RelatedIndicator',
                'id': str(effect.id),
            }],
        }
    }
    assert data == expected


def test_indicator_dimension_node(graphql_client_query_data):
    indicator = IndicatorFactory()
    dimension = DimensionFactory()
    indicator_dimension = IndicatorDimensionFactory(indicator=indicator, dimension=dimension)
    data = graphql_client_query_data(
        '''
        query($indicator: ID!) {
          indicator(id: $indicator) {
            dimensions {
              __typename
              id
              dimension {
                __typename
                id
              }
              indicator {
                __typename
                id
              }
              order
            }
          }
        }
        ''',
        variables=dict(indicator=indicator.id)
    )
    expected = {
        'indicator': {
            'dimensions': [{
                '__typename': 'IndicatorDimension',
                'id': str(indicator_dimension.id),
                'dimension': {
                    '__typename': 'Dimension',
                    'id': str(dimension.id),
                },
                'indicator': {
                    '__typename': 'Indicator',
                    'id': str(indicator.id),
                },
                'order': 1,
            }]
        }
    }
    assert data == expected


def test_plan_indicators_has_goals_parameter(graphql_client_query_data):
    plan = PlanFactory()
    indicators = [
        (IndicatorFactory(), False),
        (IndicatorGoalFactory().indicator, True)
    ]
    for indicator, has_goals in indicators:
        indicator.plans.add(plan)
    for indicator, has_goals in indicators:
        data = graphql_client_query_data(
            '''
            query($plan: ID!, $has_goals: Boolean!) {
              planIndicators(plan: $plan, hasGoals: $has_goals) {
                id
              }
            }
            ''',
            variables=dict(plan=plan.identifier, has_goals=has_goals)
        )
        expected = {
            'planIndicators': [
                {
                    'id': str(indicator.id)
                }
            ]
        }
        assert data == expected
