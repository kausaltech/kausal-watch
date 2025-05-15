import pytest

from aplans.utils import hyphenate_fi

from actions.tests.factories import (
    ActionFactory,
    ActionResponsiblePartyFactory,
    ActionScheduleFactory,
    CategoryFactory,
    PlanFactory,
)

pytestmark = pytest.mark.django_db

ACTION_FRAGMENT = """
    fragment ActionFragment on Action {
      id
      identifier
      name(hyphenated: true)
      officialName
      completion
      plan {
        id
      }
      schedule {
        id
      }
      status {
        id
        identifier
        name
      }
      manualStatusReason
      implementationPhase {
        id
        identifier
        name
      }
      impact {
        id
        identifier
      }
      categories {
        id
      }
      responsibleParties {
        id
        organization {
          id
          abbreviation
          name
        }
      }
      mergedWith {
        id
        identifier
      }
    }
    """


def test_planactions(graphql_client_query_data):
    plan = PlanFactory()
    schedule = ActionScheduleFactory(plan=plan)
    category = CategoryFactory()
    action = ActionFactory(plan=plan,
                           categories=[category],
                           schedule=[schedule])
    responsible_party = ActionResponsiblePartyFactory(action=action, organization=plan.organization)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planActions(plan: $plan) {
            ...ActionFragment
          }
        }
        """ + ACTION_FRAGMENT,
        variables=dict(plan=plan.identifier),
    )
    expected = {
        'planActions': [{
            'id': str(action.id),
            'identifier': action.identifier,
            'name': hyphenate_fi(action.name),
            'officialName': action.official_name,
            'completion': action.completion,
            'plan': {
                'id': str(plan.identifier),  # TBD: Why not use the `id` field as we do for most other models?
            },
            'schedule': [{
                'id': str(schedule.id),
            }],
            'status': {
                'id': str(action.status.id),
                'identifier': action.status.identifier,
                'name': action.status.name,
            },
            'manualStatusReason': action.manual_status_reason,
            'implementationPhase': {
                'id': str(action.implementation_phase.id),
                'identifier': action.implementation_phase.identifier,
                'name': action.implementation_phase.name,
            },
            'impact': {
                'id': str(action.impact.id),
                'identifier': action.impact.identifier,
            },
            'categories': [{
                'id': str(category.id),
            }],
            'responsibleParties': [{
                'id': str(responsible_party.id),
                'organization': {
                    'id': str(action.plan.organization.id),
                    'abbreviation': action.plan.organization.abbreviation,
                    'name': action.plan.organization.name,
                },
            }],
            'mergedWith': None,
        }],
    }
    assert data == expected


def test_action_has_dependency_relationships(
    graphql_client_query_data, plan, action_factory, action_dependency_role_factory, action_dependency_relationship_factory
):
    """Test the has_dependency_relationships field in the planActions GraphQL query."""
    action_dependency_role_factory(plan=plan)

    action1 = action_factory(plan=plan)
    action2 = action_factory(plan=plan)
    action3 = action_factory(plan=plan)

    action_dependency_relationship_factory(preceding=action1, dependent=action2)

    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planActions(plan: $plan) {
            id
            identifier
            hasDependencyRelationships
          }
        }
        """,
        variables=dict(plan=plan.identifier),
    )

    actions_data = {action['identifier']: action for action in data['planActions']}
    assert actions_data[action1.identifier]['hasDependencyRelationships'] is True
    assert actions_data[action2.identifier]['hasDependencyRelationships'] is True
    assert actions_data[action3.identifier]['hasDependencyRelationships'] is False


def test_action_has_dependency_relationships_no_roles(
    graphql_client_query_data, plan_factory, action_factory
):
    """Test that has_dependency_relationships returns False when plan has no dependency roles."""
    # Setup: Create a plan without any dependency roles
    plan_without_roles = plan_factory()

    # Create actions in the plan
    action1 = action_factory(plan=plan_without_roles)
    action2 = action_factory(plan=plan_without_roles)
    action3 = action_factory(plan=plan_without_roles)

    # Query for actions with has_dependency_relationships field
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planActions(plan: $plan) {
            id
            identifier
            hasDependencyRelationships
          }
        }
        """,
        variables=dict(plan=plan_without_roles.identifier),
    )

    # Extract the results for easier assertion
    actions_data = {action['identifier']: action for action in data['planActions']}

    # Assertions - all actions should have hasDependencyRelationships=False
    # since the plan has no dependency roles configured
    assert actions_data[action1.identifier]['hasDependencyRelationships'] is False
    assert actions_data[action2.identifier]['hasDependencyRelationships'] is False
    assert actions_data[action3.identifier]['hasDependencyRelationships'] is False


def test_action_has_dependency_relationships_via_plan(
    graphql_client_query_data, plan, action_factory, action_dependency_role_factory, action_dependency_relationship_factory
):
    """Test has_dependency_relationships via plan { actions } GraphQL query."""
    # Setup: Create plan with action dependency roles to enable dependency relationships
    action_dependency_role_factory(plan=plan)

    # Create actions
    action1 = action_factory(plan=plan)
    action2 = action_factory(plan=plan)
    action3 = action_factory(plan=plan)

    # Create a dependency relationship between action1 and action2
    action_dependency_relationship_factory(preceding=action1, dependent=action2)

    # Query for actions with has_dependency_relationships field using plan.actions
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          plan(id: $plan) {
            actions {
              id
              identifier
              hasDependencyRelationships
            }
          }
        }
        """,
        variables=dict(plan=plan.identifier),
    )

    # Extract the results for easier assertion
    actions_data = {action['identifier']: action for action in data['plan']['actions']}

    # Assertions - same as before, but queried through plan.actions
    assert actions_data[action1.identifier]['hasDependencyRelationships'] is True
    assert actions_data[action2.identifier]['hasDependencyRelationships'] is True
    assert actions_data[action3.identifier]['hasDependencyRelationships'] is False
