import pytest

from aplans.utils import hyphenate

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


@pytest.mark.django_db
def test_planactions(graphql_client_query_data, plan, action, action_schedule, category,
                     action_responsible_party):
    action.schedule.add(action_schedule)
    action.categories.add(category)
    action.responsible_parties.add(action_responsible_party)
    assert action.schedule.count() == 1
    schedule = action.schedule.first()
    assert action.categories.count() == 1
    category = action.categories.first()
    assert action.responsible_parties.count() == 1
    responsible_party = action.responsible_parties.first()
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
            'manualStatusReason': None,
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
