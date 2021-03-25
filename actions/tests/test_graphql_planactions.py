import pytest

from aplans.utils import hyphenate

from actions.tests.factories import (
    ActionFactory, ActionScheduleFactory, ActionResponsiblePartyFactory, CategoryFactory, PlanFactory
)

pytestmark = pytest.mark.django_db

ACTION_FRAGMENT = '''
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
    '''


def test_planactions(graphql_client_query_data):
    plan = PlanFactory()
    schedule = ActionScheduleFactory(plan=plan)
    category = CategoryFactory()
    action = ActionFactory(plan=plan,
                           categories=[category],
                           schedule=[schedule])
    responsible_party = ActionResponsiblePartyFactory(action=action, organization=plan.organization)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planActions(plan: $plan) {
            ...ActionFragment
          }
        }
        ''' + ACTION_FRAGMENT,
        variables=dict(plan=plan.identifier)
    )
    expected = {
        'planActions': [{
            'id': str(action.id),
            'identifier': action.identifier,
            'name': hyphenate(action.name),
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
        }]
    }
    assert data == expected
