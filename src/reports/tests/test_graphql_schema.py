import pytest

from .fixtures import *

pytestmark = pytest.mark.django_db

VALUES_FOR_ACTION_QUERY = """
    query($plan: ID!, $actionId: ID, $actionIdentifier: ID) {
      plan(id: $plan) {
        reportTypes {
          reports {
            valuesForAction(actionId: $actionId, actionIdentifier: $actionIdentifier) {
              __typename
            }
          }
        }
      }
    }
    """


def query_values_for_action(graphql_client_query_data, plan, action_identifier=None, action_id=None):
    data = graphql_client_query_data(
        VALUES_FOR_ACTION_QUERY,
        variables=dict(plan=plan.identifier, actionId=action_id, actionIdentifier=action_identifier),
    )
    reports = data['plan']['reportTypes'][0]['reports']
    assert reports
    return [report['valuesForAction'] for report in reports]


@pytest.mark.usefixtures('plan_with_report_and_attributes')
def test_values_for_action_unknown_identifier(graphql_client_query_data, plan):
    values = query_values_for_action(graphql_client_query_data, plan, 'foobar')
    assert all(v is None for v in values)


@pytest.mark.usefixtures('plan_with_report_and_attributes')
def test_values_for_action_with_snapshot(graphql_client_query_data, plan, report_with_all_attributes, user):
    action = plan.actions.first()
    action.mark_as_complete_for_report(report_with_all_attributes, user)
    values = query_values_for_action(graphql_client_query_data, plan, action.identifier)
    assert any(v for v in values)


@pytest.mark.usefixtures('plan_with_report_and_attributes')
def test_values_for_action_without_snapshot(graphql_client_query_data, plan):
    action = plan.actions.first()
    values = query_values_for_action(graphql_client_query_data, plan, action.identifier)
    assert all(v is None for v in values)


@pytest.mark.usefixtures('plan_with_report_and_attributes')
def test_values_for_action_unknown_id(graphql_client_query_data, plan):
    values = query_values_for_action(graphql_client_query_data, plan, action_id='foobar')
    assert all(v is None for v in values)
