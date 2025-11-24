import json
from datetime import timedelta
from typing import Any

from django.utils import timezone

import pytest

from aplans.utils import RestrictedVisibilityModel

from actions.tests.factories import ActionFactory, CategoryFactory, PlanFactory
from indicators.tests.factories import (
    ActionIndicatorFactory,
    CommonIndicatorFactory,
    DimensionCategoryFactory,
    DimensionFactory,
    IndicatorDimensionFactory,
    IndicatorFactory,
    IndicatorGoalFactory,
    IndicatorGraphFactory,
    IndicatorLevelFactory,
    IndicatorValueFactory,
    QuantityFactory,
    RelatedIndicatorFactory,
    UnitFactory,
)

pytestmark = pytest.mark.django_db


def test_unit_node(graphql_client_query_data):
    unit = UnitFactory.create()
    indicator = IndicatorFactory.create(unit=unit)
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(indicator=indicator.id),
    )
    expected = {
        'indicator': {
            'unit': {
                '__typename': 'Unit',
                'id': str(unit.pk),
                'name': unit.name,
                'shortName': unit.short_name,
                'verboseName': unit.verbose_name,
                'verboseNamePlural': unit.verbose_name_plural,
            },
        },
    }
    assert data == expected


def test_quantity_node(graphql_client_query_data):
    quantity = QuantityFactory.create()
    indicator = IndicatorFactory.create(quantity=quantity)
    data = graphql_client_query_data(
        """
        query($indicator: ID!) {
          indicator(id: $indicator) {
            quantity {
              __typename
              id
              name
            }
          }
        }
        """,
        variables=dict(indicator=indicator.pk),
    )
    expected = {
        'indicator': {
            'quantity': {
                '__typename': 'Quantity',
                'id': str(quantity.pk),
                'name': quantity.name,
            },
        },
    }
    assert data == expected


def test_related_indicator_node(graphql_client_query_data):
    related_indicator = RelatedIndicatorFactory.create()
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(indicator=related_indicator.causal_indicator.id),
    )
    expected = {
        'indicator': {
            'relatedEffects': [
                {
                    '__typename': 'RelatedIndicator',
                    'id': str(related_indicator.pk),
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
                }
            ],
        },
    }
    assert data == expected


@pytest.mark.parametrize('published_at', [None, timezone.now() - timedelta(days=1)])
@pytest.mark.parametrize('expose_to_auth_only', [False, True])
def test_action_indicator_node(graphql_client_query_data, published_at, expose_to_auth_only):
    indicator = IndicatorFactory.create()
    plan = PlanFactory.create(
        published_at=published_at, features__expose_unpublished_plan_only_to_authenticated_user=expose_to_auth_only
    )
    action = ActionFactory.create(plan=plan)
    action_indicator = ActionIndicatorFactory.create(indicator=indicator, action=action)
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(indicator=indicator.id),
    )
    expected = {
        'indicator': {
            'relatedActions': [
                {
                    '__typename': 'ActionIndicator',
                    'id': str(action_indicator.pk),
                    'action': {
                        '__typename': 'Action',
                        'id': str(action_indicator.action.pk),
                    },
                    'indicator': {
                        '__typename': 'Indicator',
                        'id': str(action_indicator.indicator.id),
                    },
                    'effectType': action_indicator.effect_type.upper(),
                    'indicatesActionProgress': action_indicator.indicates_action_progress,
                }
            ]
            if published_at or not expose_to_auth_only
            else [],
        },
    }
    assert data == expected


def test_indicator_graph_node(graphql_client_query_data):
    indicator = IndicatorFactory.create()
    indicator_graph = IndicatorGraphFactory.create(indicator=indicator)
    indicator.latest_graph = indicator_graph
    indicator.save(update_fields=['latest_graph'])
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(indicator=indicator.id),
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
            },
        },
    }
    assert data == expected


def test_indicator_level_node(graphql_client_query_data):
    plan = PlanFactory.create()
    indicator_level = IndicatorLevelFactory.create(plan=plan)
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(plan=plan.identifier),
    )
    expected = {
        'plan': {
            'indicatorLevels': [
                {
                    '__typename': 'IndicatorLevel',
                    'id': str(indicator_level.pk),
                    'indicator': {
                        '__typename': 'Indicator',
                        'id': str(indicator_level.indicator.pk),
                    },
                    'plan': {
                        '__typename': 'Plan',
                        'id': str(plan.identifier),
                    },
                    'level': indicator_level.level.upper(),
                }
            ],
        },
    }
    assert data == expected


def test_dimension_node(graphql_client_query_data):
    indicator = IndicatorFactory.create()
    dimension = DimensionFactory.create()
    IndicatorDimensionFactory.create(indicator=indicator, dimension=dimension)
    dimension_category = DimensionCategoryFactory.create(dimension=dimension)
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(indicator=indicator.pk),
    )
    expected = {
        'indicator': {
            'dimensions': [
                {
                    'dimension': {
                        '__typename': 'Dimension',
                        'id': str(dimension.pk),
                        'name': dimension.name,
                        'categories': [
                            {
                                '__typename': 'DimensionCategory',
                                'id': str(dimension_category.pk),
                            }
                        ],
                    },
                }
            ],
        },
    }
    assert data == expected


def test_dimension_category_node(graphql_client_query_data):
    indicator = IndicatorFactory.create()
    dimension = DimensionFactory.create()
    IndicatorDimensionFactory.create(indicator=indicator, dimension=dimension)
    dimension_category = DimensionCategoryFactory.create(dimension=dimension)
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(indicator=indicator.pk),
    )
    expected = {
        'indicator': {
            'dimensions': [
                {
                    'dimension': {
                        'id': str(dimension.pk),
                        'categories': [
                            {
                                '__typename': 'DimensionCategory',
                                'id': str(dimension_category.pk),
                                'dimension': {
                                    '__typename': 'Dimension',
                                    'id': str(dimension.pk),
                                },
                                'name': dimension_category.name,
                                'order': 1,
                            }
                        ],
                    },
                }
            ],
        },
    }
    assert data == expected


def test_framework_node(graphql_client_query_data):
    # FIXME: FrameworkNode does not appear in a schema
    pass


def test_common_indicator_node(graphql_client_query_data):
    common_indicator = CommonIndicatorFactory.create()
    indicator = IndicatorFactory.create(common=common_indicator)
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(indicator=indicator.pk),
    )
    expected = {
        'indicator': {
            'common': {
                '__typename': 'CommonIndicator',
                'id': str(common_indicator.pk),
                'identifier': common_indicator.identifier,
                'name': common_indicator.name,
                'description': str(common_indicator.description),
                'quantity': {
                    '__typename': 'Quantity',
                    'id': str(common_indicator.quantity.pk),
                },
                'unit': {
                    '__typename': 'Unit',
                    'id': str(common_indicator.unit.pk),
                },
            },
        },
    }
    assert data == expected


def test_framework_indicator_node(graphql_client_query):
    # FIXME: FrameworkIndicatorNode does not appear in a schema
    pass


def test_indicator_value_node(graphql_client_query_data):
    category = DimensionCategoryFactory.create()
    indicator = IndicatorFactory.create()
    indicator_value = IndicatorValueFactory.create(indicator=indicator, categories=[category])
    indicator.latest_value = indicator_value
    indicator.save(update_fields=['latest_value'])
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(indicator=indicator.pk),
    )
    expected = {
        'indicator': {
            'latestValue': {
                '__typename': 'IndicatorValue',
                'id': str(indicator_value.pk),
                'indicator': {
                    '__typename': 'Indicator',
                    'id': str(indicator.pk),
                },
                'value': indicator_value.value,
                'date': indicator_value.date.isoformat(),
            },
        },
    }
    assert data == expected


def test_indicator_goal_node(graphql_client_query_data):
    indicator = IndicatorFactory.create()
    indicator_goal = IndicatorGoalFactory.create(indicator=indicator)
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(indicator=indicator.pk),
    )
    expected = {
        'indicator': {
            'goals': [
                {
                    '__typename': 'IndicatorGoal',
                    'id': str(indicator_goal.pk),
                    'indicator': {
                        '__typename': 'Indicator',
                        'id': str(indicator.pk),
                    },
                    'scenario': None,
                    'value': indicator_goal.value,
                    'date': indicator_goal.date.isoformat(),
                }
            ],
        },
    }
    assert data == expected


def test_indicator_node(graphql_client_query_data):
    plan = PlanFactory.create()
    indicator = IndicatorFactory.create()
    indicator_goal = IndicatorGoalFactory.create(indicator=indicator)
    indicator_value = IndicatorValueFactory.create(indicator=indicator)
    indicator_graph = IndicatorGraphFactory.create(indicator=indicator)
    indicator.latest_value = indicator_value
    indicator.latest_graph = indicator_graph
    indicator.save(update_fields=['latest_value', 'latest_graph'])
    action = ActionFactory.create(plan=plan)
    action_indicator = ActionIndicatorFactory.create(action=action, indicator=indicator)
    category = CategoryFactory.create()
    indicator.categories.add(category)
    indicator.save()
    indicator_dimension = IndicatorDimensionFactory.create(indicator=indicator)
    # Create IndicatorLevel so that `plan` appears in `indicator.plan`
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    assert indicator.common is not None
    assert indicator.quantity is not None
    data = graphql_client_query_data(
        """
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
            showTrendline
            desiredTrend
            showTotalLine
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
        """,
        variables=dict(indicator=indicator.pk),
    )
    expected = {
        'indicator': {
            '__typename': 'Indicator',
            'id': str(indicator.pk),
            'common': {
                '__typename': 'CommonIndicator',
                'id': str(indicator.common.pk),
            },
            'organization': {
                '__typename': 'Organization',
                'id': str(indicator.organization.pk),
            },
            'identifier': indicator.identifier,
            'name': indicator.name,
            'quantity': {
                '__typename': 'Quantity',
                'id': str(indicator.quantity.pk),
            },
            'unit': {
                '__typename': 'Unit',
                'id': str(indicator.unit.pk),
            },
            'description': indicator.description,
            'minValue': indicator.min_value,
            'maxValue': indicator.max_value,
            'showTrendline': indicator.show_trendline,
            'desiredTrend': indicator.desired_trend.upper(),
            'showTotalLine': indicator.show_total_line,
            'categories': [
                {
                    '__typename': 'Category',
                    'id': str(category.pk),
                }
            ],
            'timeResolution': indicator.time_resolution.upper(),
            'reference': indicator.reference,
            'latestValue': {
                '__typename': 'IndicatorValue',
                'id': str(indicator.latest_value.pk),
            },
            'latestGraph': {
                '__typename': 'IndicatorGraph',
                'id': str(indicator.latest_graph.pk),
            },
            'updatedAt': indicator.updated_at.isoformat(),
            'createdAt': indicator.created_at.isoformat(),
            'values': [
                {
                    '__typename': 'IndicatorValue',
                    'id': str(indicator.latest_value.pk),
                }
            ],
            'plans': [
                {
                    '__typename': 'Plan',
                    'id': str(plan.identifier),
                }
            ],
            'goals': [
                {
                    '__typename': 'IndicatorGoal',
                    'id': str(indicator_goal.pk),
                }
            ],
            'relatedActions': [
                {
                    '__typename': 'ActionIndicator',
                    'id': str(action_indicator.pk),
                }
            ],
            'actions': [
                {
                    '__typename': 'Action',
                    'id': str(action.pk),
                }
            ],
            'dimensions': [
                {
                    '__typename': 'IndicatorDimension',
                    'id': str(indicator_dimension.pk),
                }
            ],
        },
    }
    assert data == expected


def test_indicator_node_cause_effect(graphql_client_query_data):
    indicator = IndicatorFactory.create()
    cause = RelatedIndicatorFactory.create(effect_indicator=indicator)
    effect = RelatedIndicatorFactory.create(causal_indicator=indicator)
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(indicator=indicator.pk),
    )
    expected = {
        'indicator': {
            '__typename': 'Indicator',
            'id': str(indicator.pk),
            'relatedCauses': [
                {
                    '__typename': 'RelatedIndicator',
                    'id': str(cause.pk),
                }
            ],
            'relatedEffects': [
                {
                    '__typename': 'RelatedIndicator',
                    'id': str(effect.pk),
                }
            ],
        },
    }
    assert data == expected


def test_indicator_dimension_node(graphql_client_query_data):
    indicator = IndicatorFactory.create()
    dimension = DimensionFactory.create()
    indicator_dimension = IndicatorDimensionFactory.create(indicator=indicator, dimension=dimension)
    data = graphql_client_query_data(
        """
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
        """,
        variables=dict(indicator=indicator.pk),
    )
    expected = {
        'indicator': {
            'dimensions': [
                {
                    '__typename': 'IndicatorDimension',
                    'id': str(indicator_dimension.pk),
                    'dimension': {
                        '__typename': 'Dimension',
                        'id': str(dimension.pk),
                    },
                    'indicator': {
                        '__typename': 'Indicator',
                        'id': str(indicator.pk),
                    },
                    'order': 1,
                }
            ],
        },
    }
    assert data == expected


def test_plan_indicators_has_goals_parameter(graphql_client_query_data):
    plan = PlanFactory.create()
    indicators = [
        (IndicatorFactory.create(), False),
        (IndicatorGoalFactory.create().indicator, True),
    ]
    for indicator, _has_goals in indicators:
        indicator.plans.add(plan)
    for indicator, has_goals in indicators:
        data = graphql_client_query_data(
            """
            query($plan: ID!, $has_goals: Boolean!) {
              planIndicators(plan: $plan, hasGoals: $has_goals) {
                id
              }
            }
            """,
            variables=dict(plan=plan.identifier, has_goals=has_goals),
        )
        expected = {
            'planIndicators': [
                {
                    'id': str(indicator.id),
                },
            ],
        }
        assert data == expected


def test_indicator_visibility(graphql_client_query_data):
    plan = PlanFactory.create()
    public_indicator = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
    internal_indicator = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)

    IndicatorLevelFactory.create(indicator=public_indicator, plan=plan)
    IndicatorLevelFactory.create(indicator=internal_indicator, plan=plan)

    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planIndicators(plan: $plan) {
            id
            name
          }
        }
        """,
        variables=dict(plan=plan.identifier),
    )

    expected = {
        'planIndicators': [
            {
                'id': str(public_indicator.pk),
                'name': public_indicator.name,
            },
        ],
    }
    assert data == expected


def test_indicator_query_visibility(graphql_client_query_data):
    plan = PlanFactory.create()
    public_indicator = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
    internal_indicator = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)

    IndicatorLevelFactory.create(indicator=public_indicator, plan=plan)
    IndicatorLevelFactory.create(indicator=internal_indicator, plan=plan)

    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            id
            name
          }
        }
        """,
        variables={'id': public_indicator.pk},
    )

    expected: dict[str, Any]
    expected = {
        'indicator': {
            'id': str(public_indicator.pk),
            'name': public_indicator.name,
        },
    }
    assert data == expected

    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            id
            name
          }
        }
        """,
        variables={'id': internal_indicator.id},
    )

    expected = {
        'indicator': None,
    }
    assert data == expected


def test_related_indicators_visibility(graphql_client_query_data):
    plan = PlanFactory.create()
    public_indicator = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
    internal_indicator = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)

    IndicatorLevelFactory.create(indicator=public_indicator, plan=plan)
    IndicatorLevelFactory.create(indicator=internal_indicator, plan=plan)

    public_cause = RelatedIndicatorFactory.create(
        effect_indicator=public_indicator, causal_indicator__visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC
    )
    public_effect = RelatedIndicatorFactory.create(
        causal_indicator=public_indicator, effect_indicator__visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC
    )
    RelatedIndicatorFactory.create(
        effect_indicator=public_indicator, causal_indicator__visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL
    )
    RelatedIndicatorFactory.create(
        causal_indicator=public_indicator, effect_indicator__visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL
    )

    data = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            id
            relatedCauses {
              id
            }
            relatedEffects {
              id
            }
          }
        }
        """,
        variables={'id': public_indicator.pk},
    )

    expected = {
        'indicator': {
            'id': str(public_indicator.pk),
            'relatedCauses': [{'id': str(public_cause.pk)}],
            'relatedEffects': [{'id': str(public_effect.pk)}],
        },
    }
    assert data == expected


@pytest.mark.parametrize(
    'published_at',
    [
        timezone.now() - timedelta(days=1),  # Published
        None,  # Unpublished
    ],
)
@pytest.mark.parametrize('expose_to_auth_only', [False, True])
def test_indicator_plans_visibility(graphql_client_query_data, published_at, expose_to_auth_only):
    """Test plan visibility in indicator's plans field for unauthenticated users."""
    plan = PlanFactory.create(
        published_at=published_at, features__expose_unpublished_plan_only_to_authenticated_user=expose_to_auth_only
    )
    indicator = IndicatorFactory.create()
    indicator.plans.add(plan)

    response = graphql_client_query_data(
        """
        query($id: ID!) {
          indicator(id: $id) {
            plans {
              id
            }
          }
        }
        """,
        variables={'id': str(indicator.id)},
    )

    expected = {
        'indicator': {
            'plans': [
                {
                    'id': plan.identifier,
                }
            ]
            if published_at or not expose_to_auth_only
            else [],
        }
    }

    assert response == expected
