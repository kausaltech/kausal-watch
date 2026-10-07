import pytest

from actions.attributes import DraftAttributes
from actions.tests.factories import ActionFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def query_action_workflow_status():
    return """
      query ($id: ID!, $lang: String!) @locale(lang: $lang) {
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
    """


def test_workflow_status_exposed_for_action(
    graphql_client_query_data,
    query_action_workflow_status,
    plan_with_single_task_moderation,
    person,
    client,
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
        variables={'id': action.id, 'lang': 'en'},
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
    client,
):
    action = plan_with_single_task_moderation.actions.first()
    action.draft_attributes = DraftAttributes()
    user = person.user
    action.save_revision(user=user)
    workflow = plan_with_single_task_moderation.features.moderation_workflow
    workflow.start(action, user=user)

    assert plan != plan_with_single_task_moderation
    person.general_admin_plans.add(plan)
    client.force_login(user)

    data = graphql_client_query(query_action_workflow_status, variables={'id': action.id, 'lang': 'en'})
    assert data['data']['action']['workflowStatus'] is None


@pytest.mark.parametrize('state', ['DRAFT', 'APPROVED'])
def test_plan_actions_first_with_workflow_state(
    graphql_client_query_data, plan_with_double_task_moderation, person, client, state
):
    # The draft and approved paths filter the actions further, which used to fail once `first` had sliced them.
    # (Two tasks, because with a single task the approved path currently returns no actions at all.)
    plan = plan_with_double_task_moderation
    plan.features.save()
    first_action = plan.actions.get()
    second_action = ActionFactory.create(plan=plan, order=first_action.order + 1)
    ActionFactory.create(plan=plan, order=first_action.order + 2)
    user = person.user
    person.general_admin_plans.add(plan)
    second_action.name = 'Draft name'
    second_action.save_revision(user=user)
    plan.features.moderation_workflow.start(second_action, user=user)
    client.force_login(user)

    data = graphql_client_query_data(
        f"""
        query($plan: ID!) @workflow(state: {state}) {{
          planActions(plan: $plan, first: 2) {{
            identifier
            name
          }}
        }}
        """,
        variables={'plan': plan.identifier},
    )

    second_name = 'Draft name' if state == 'DRAFT' else second_action.name
    assert data['planActions'] == [
        {'identifier': first_action.identifier, 'name': first_action.name},
        {'identifier': second_action.identifier, 'name': second_name},
    ]
