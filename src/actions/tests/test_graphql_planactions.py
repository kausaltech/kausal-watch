from django.db import connection
from django.test.utils import CaptureQueriesContext

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
    plan = PlanFactory.create()
    schedule = ActionScheduleFactory.create(plan=plan)
    category = CategoryFactory.create()
    action = ActionFactory.create(
        plan=plan,
        categories=[category],
        schedule=[schedule],
    )
    responsible_party = ActionResponsiblePartyFactory.create(action=action, organization=plan.organization)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planActions(plan: $plan) {
            ...ActionFragment
          }
        }
        """
        + ACTION_FRAGMENT,
        variables=dict(plan=plan.identifier),
    )
    assert action.status is not None
    assert action.implementation_phase is not None
    assert action.impact is not None
    expected = {
        'planActions': [
            {
                'id': str(action.id),
                'identifier': action.identifier,
                'name': hyphenate_fi(action.name),
                'officialName': action.official_name,
                'completion': action.completion,
                'plan': {
                    'id': str(plan.identifier),  # TBD: Why not use the `id` field as we do for most other models?
                },
                'schedule': [
                    {
                        'id': str(schedule.id),
                    }
                ],
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
                'categories': [
                    {
                        'id': str(category.id),
                    }
                ],
                'responsibleParties': [
                    {
                        'id': str(responsible_party.id),
                        'organization': {
                            'id': str(action.plan.organization.id),
                            'abbreviation': action.plan.organization.abbreviation,
                            'name': action.plan.organization.name,
                        },
                    }
                ],
                'mergedWith': None,
            }
        ],
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


def test_action_has_dependency_relationships_no_roles(graphql_client_query_data, plan_factory, action_factory):
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


@pytest.mark.parametrize(('field', 'attr'), [('description', 'description'), ('leadParagraph', 'lead_paragraph')])
def test_planactions_translated_field_without_id_or_name(graphql_client_query_data, field, attr):
    # Selecting a translated field next to only plain model fields (no `id`, no `name`) used to make the query
    # optimizer defer `i18n`, so the resolver raised.
    plan = PlanFactory.create()
    action = ActionFactory.create(plan=plan)
    data = graphql_client_query_data(
        f"""
        query($plan: ID!) {{
          planActions(plan: $plan) {{
            identifier
            {field}
          }}
        }}
        """,
        variables=dict(plan=plan.identifier),
    )
    assert data == {'planActions': [{'identifier': action.identifier, field: getattr(action, attr)}]}


@pytest.mark.parametrize('field', ['description', 'leadParagraph'])
def test_planactions_translated_field_does_not_load_plan_per_action(graphql_client_query_data, field):
    # The translation's fallback language comes from `plan__primary_language_lowercase`; if the resolver's hints
    # don't join `plan`, every action loads it lazily.
    plan = PlanFactory.create()
    query = f'query($plan: ID!) {{ planActions(plan: $plan) {{ identifier {field} }} }}'

    def count_plan_queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            graphql_client_query_data(query, variables=dict(plan=plan.identifier))
        return sum(
            1 for q in ctx.captured_queries if 'FROM "actions_plan"' in q['sql'] or '"plan_id" FROM "actions_action"' in q['sql']
        )

    ActionFactory.create(plan=plan)
    plan_queries_for_one = count_plan_queries()
    for _ in range(3):
        ActionFactory.create(plan=plan)
    assert count_plan_queries() == plan_queries_for_one


@pytest.mark.parametrize(
    ('draft', 'first'),
    [(False, None), (False, 10), (True, None)],
    ids=['published', 'published-first', 'draft'],
)
def test_planactions_narrow_selection_query_count_does_not_grow(
    graphql_client_query, client, plan, plan_admin_user, draft, first
):
    # The optimizer narrows the queryset to the selected columns, but the resolver itself reads the actions' foreign
    # keys (and, on the draft path, `order`); those must not be loaded lazily per action.
    directive = '@workflow(state: DRAFT)' if draft else ''
    first_arg = f', first: {first}' if first else ''
    query = f'query($plan: ID!) {directive} {{ planActions(plan: $plan{first_arg}) {{ identifier }} }}'
    if draft:
        client.force_login(plan_admin_user)

    def count_queries() -> int:
        with CaptureQueriesContext(connection) as ctx:
            response = graphql_client_query(query, variables=dict(plan=plan.identifier))
        assert 'errors' not in response, response
        return len(ctx.captured_queries)

    ActionFactory.create(plan=plan)
    count_queries()  # The first request also fills per-process caches.
    queries_for_one = count_queries()
    for _ in range(3):
        ActionFactory.create(plan=plan)
    assert count_queries() == queries_for_one
