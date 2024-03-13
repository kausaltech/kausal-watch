import itertools
import pytest


from actions.models.action import ActionContactPerson
from indicators.models import Indicator


pytestmark = pytest.mark.django_db


ACTION_FIELDS = '''
  id
  identifier
  name
  mergedWith { id }
  mergedActions { id }
  supersededBy { id },
  supersededActions { id },
  nextAction { id },
  previousAction { id },
  relatedActions { id }

'''


RETRIEVE_ACTION_QUERY = f'''
  query($id: ID) {{
    action(id: $id) {{
      {ACTION_FIELDS}
    }}
  }}
'''


RETRIEVE_INDICATOR_QUERY = f'''
  query($id: ID) {{
    indicator(id: $id) {{
      id
      relatedActions {{
        action {{
          {ACTION_FIELDS}
        }}
      }}
      actions {{
        {ACTION_FIELDS}
      }}
    }}
  }}
'''


PLAN_ACTIONS_QUERY = f'''
  query($plan: ID!) {{
    planActions(plan: $plan) {{
      {ACTION_FIELDS}
    }}
  }}
'''


PLAN_QUERY = f'''
  query($plan: ID!) {{
    plan(id: $plan) {{
      actions {{
        {ACTION_FIELDS}
      }}
    }}
  }}
'''


ACTION_FIELDS_WITH_ACTIONS = [
    'mergedWith',
    'mergedActions',
    'supersededBy',
    'supersededActions',
    'nextAction',
    'previousAction',
    'relatedActions'
]


@pytest.mark.parametrize('visibility', itertools.product(('draft', 'public'), repeat=2))
def test_action_visibility(graphql_client_query_data, actions_with_relations_factory, visibility):
    draft_actions, public_actions = actions_with_relations_factory(*visibility)
    actions = draft_actions + public_actions

    graphql_action_listings = [
        graphql_client_query_data(
            PLAN_ACTIONS_QUERY,
            variables={'plan': actions[0].plan.identifier}
        )['planActions'],
        graphql_client_query_data(
            PLAN_QUERY,
            variables={'plan': actions[0].plan.identifier}
        )['plan']['actions']
    ]

    individual_data = {
        a.id: graphql_client_query_data(RETRIEVE_ACTION_QUERY, variables={'id': str(a.id)})
        for a in actions
    }

    for action in actions:
        should_be_public = False
        if action.visibility == 'public':
            should_be_public = True

        for listing in graphql_action_listings:
            assert _action_in_list(action, listing) is should_be_public
        assert _action_visible(action, individual_data[action.id]) is should_be_public

        if should_be_public:
            continue

        for other_action in public_actions:
            if other_action.id == action.id:
                continue
            for field_name in ACTION_FIELDS_WITH_ACTIONS:
                api_object = individual_data[other_action.id]['action']
                value = api_object.get(field_name)
                if isinstance(value, list):
                    assert str(action.id) not in set((a['id'] for a in value)), field_name
                elif isinstance(value, dict):
                    assert str(action.id) != value['id'], field_name

        # ActionIndicator.action
        for indicator in Indicator.objects.all():
            data = graphql_client_query_data(
                RETRIEVE_INDICATOR_QUERY, variables={'id': indicator.id}
            )
            assert data['indicator']['id'] == str(indicator.id)
            assert str(action.id) not in (
                a['action']['id'] for a in data['indicator']['relatedActions']
            )
            assert str(action.id) not in (
                a.get('action', {}).get('id') for a in data['indicator']['actions']
            )


def _action_visible(action, data):
    if data['action'] is None:
        return False
    return data['action']['identifier'] == action.identifier


def _action_in_list(action, data):
    for item in data:
        if item['id'] == str(action.id):
            return True
    return False


def test_action_contact_person_hide_moderators(graphql_client_query_data, plan, action, action_contact_factory):
    acp1 = action_contact_factory(action=action, role=ActionContactPerson.Role.MODERATOR)
    acp2 = action_contact_factory(action=action, role=ActionContactPerson.Role.MODERATOR)
    acp3 = action_contact_factory(action=action, role=ActionContactPerson.Role.EDITOR)

    query = '''
        query($action: ID!) {
          action(id: $action) {
            contactPersons {
              __typename
              id
              action {
                __typename
                id
              }
              person {
                __typename
                id
              }
              order
              primaryContact
            }
          }
        }
        '''

    data = graphql_client_query_data(query, variables={'action': action.id})
    expected = {
        'action': {
            'contactPersons': [{
                '__typename': 'ActionContactPerson',
                'id': str(acp.id),
                'action': {
                   '__typename': 'Action',
                   'id': str(action.id),
                },
                'person': {
                   '__typename': 'Person',
                   'id': str(acp.person.id),
                },
                'order': acp.order,
                'primaryContact': acp.primary_contact,
            } for acp in [acp1, acp2, acp3]]
        }
    }
    assert data == expected

    plan.features.contact_persons_hide_moderators = True
    plan.features.save()
    data = graphql_client_query_data(query, variables={'action': action.id})
    expected = {
        'action': {
            'contactPersons': [{
                '__typename': 'ActionContactPerson',
                'id': str(acp3.id),
                'action': {
                   '__typename': 'Action',
                   'id': str(action.id),
                },
                'person': {
                   '__typename': 'Person',
                   'id': str(acp3.person.id),
                },
                'order': acp3.order,
                'primaryContact': acp3.primary_contact,
            }]
        }
    }
    assert data == expected
