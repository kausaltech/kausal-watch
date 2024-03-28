import pytest

from actions.attributes import DraftAttributes
from aplans.graphql_errors import ErrorCode

pytestmark = pytest.mark.django_db


@pytest.fixture
def query_action_workflow_status():
    return '''
      query ($id: ID!) {
        action(id: $id) {
          workflowStatus {
            hasUnpublishedChanges
            latestRevision {
              createdAt
            }
            currentWorkflowState {
              status
              statusMessage
            }
          }
        }
      }
    '''

def test_workflow_status_exposed_for_action(
        graphql_client_query_data,
        query_action_workflow_status,
        plan_with_single_task_moderation,
        person,
        client
):
    plan = plan_with_single_task_moderation
    action = plan.actions.first()
    action.draft_attributes = DraftAttributes()
    user = person.user
    action.save_revision(user=user)
    workflow = plan.features.moderation_workflow
    workflow.start(action, user=user)
    person.general_admin_plans.add(plan)
    person.save()

    client.force_login(user)

    data = graphql_client_query_data(
        query_action_workflow_status,
        variables={'id': action.id}
    )
    workflow_status_data = data['action']['workflowStatus']
    assert workflow_status_data['hasUnpublishedChanges'] is True
    assert isinstance(workflow_status_data['latestRevision']['createdAt'], str)
    assert workflow_status_data['currentWorkflowState']['status'] == 'IN_PROGRESS'
    assert workflow_status_data['currentWorkflowState']['statusMessage'] == 'In progress'


def test_workflow_status_not_exposed_with_no_plan_access(
        graphql_client_query,
        query_action_workflow_status,
        plan_with_single_task_moderation,
        person,
        plan,
        client
):
    action = plan_with_single_task_moderation.actions.first()
    action.draft_attributes = DraftAttributes()
    user = person.user
    action.save_revision(user=user, submitted_for_moderation=True)

    assert plan != plan_with_single_task_moderation
    person.general_admin_plans.add(plan)
    client.force_login(user)

    data = graphql_client_query(query_action_workflow_status, variables={'id': action.id})
    error =  data['errors'][0]
    assert error['extensions']['code'] == ErrorCode.ACCESS_DENIED
    assert data['data']['action']['workflowStatus'] is None
    assert error['path'] == ['action', 'workflowStatus']
