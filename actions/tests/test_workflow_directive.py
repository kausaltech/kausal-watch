import pytest

from actions.attributes import DraftAttributes

pytestmark = pytest.mark.django_db

DRAFT_ACTION_NAME = 'Draft Action Name'


@pytest.fixture
def query_single_action_draft():
    return """
      query ($id: ID!, $lang: String!) @locale(lang: $lang) @workflow(state: DRAFT) {
        action(id: $id) {
          name
        }
      }
    """


@pytest.fixture
def query_single_action_variable_state():
    return """
      query ($id: ID!, $lang: String!, $state: WorkflowState!) @locale(lang: $lang) @workflow(state: $state) {
        action(id: $id) {
          name
        }
      }
    """


@pytest.fixture
def query_single_action_no_directive():
    return """
      query ($id: ID!, $lang: String!) @locale(lang: $lang) {
        action(id: $id) {
          name
        }
      }
    """


@pytest.fixture
def query_plan_actions():
    return """
      query ($plan: ID!, $lang: String!) @locale(lang: $lang) @workflow(state: DRAFT) {
        planActions(plan: $plan) {
          name
        }
      }
    """


@pytest.fixture
def action_with_draft(plan_factory, workflow_factory, workflow_task_factory, action_factory, person):
    plan = plan_factory()
    workflow = workflow_factory()
    workflow_task_factory(workflow=workflow)
    plan.features.moderation_workflow = workflow
    plan.features.save(update_fields=['moderation_workflow'])
    action = action_factory(plan=plan)
    published_name = action.name
    user = person.user

    # Modify the action name in memory and save a draft revision
    action.name = DRAFT_ACTION_NAME
    action.draft_attributes = DraftAttributes()
    action.save_revision(user=user)

    # Start the moderation workflow so the draft is in progress
    workflow.start(action, user=user)

    # Restore the published name on the live DB record
    action.name = published_name
    action.save(update_fields=['name'])

    return action, published_name


def test_single_action_draft_for_authenticated_admin(
    graphql_client_query_data,
    query_single_action_draft,
    action_with_draft,
    person,
    client,
):
    action, _published_name = action_with_draft
    plan = action.plan
    person.general_admin_plans.add(plan)
    person.save()
    client.force_login(person.user)

    data = graphql_client_query_data(
        query_single_action_draft,
        variables={'id': action.id, 'lang': 'en'},
    )
    assert data['action']['name'] == DRAFT_ACTION_NAME


def test_single_action_published_for_unauthenticated_despite_draft_directive(
    graphql_client_query_data,
    query_single_action_draft,
    action_with_draft,
):
    action, published_name = action_with_draft

    data = graphql_client_query_data(
        query_single_action_draft,
        variables={'id': action.id, 'lang': 'en'},
    )
    assert data['action']['name'] == published_name


def test_plan_actions_draft_for_authenticated_admin(
    graphql_client_query_data,
    query_plan_actions,
    action_with_draft,
    person,
    client,
):
    action, _published_name = action_with_draft
    plan = action.plan
    person.general_admin_plans.add(plan)
    person.save()
    client.force_login(person.user)

    data = graphql_client_query_data(
        query_plan_actions,
        variables={'plan': plan.identifier, 'lang': 'en'},
    )
    actions = data['planActions']
    assert len(actions) == 1
    assert actions[0]['name'] == DRAFT_ACTION_NAME


def test_single_action_draft_via_variable_for_authenticated_admin(
    graphql_client_query_data,
    query_single_action_variable_state,
    action_with_draft,
    person,
    client,
):
    action, _published_name = action_with_draft
    plan = action.plan
    person.general_admin_plans.add(plan)
    person.save()
    client.force_login(person.user)

    data = graphql_client_query_data(
        query_single_action_variable_state,
        variables={'id': action.id, 'lang': 'en', 'state': 'DRAFT'},
    )
    assert data['action']['name'] == DRAFT_ACTION_NAME


def test_single_action_draft_with_related_actions(
    graphql_client_query_data,
    action_with_draft,
    action_factory,
    person,
    client,
):
    """Querying a draft action with relatedActions should not crash on FakeQuerySet."""
    action, _published_name = action_with_draft
    plan = action.plan
    other_action = action_factory(plan=plan)
    action.related_actions.add(other_action)
    person.general_admin_plans.add(plan)
    person.save()
    client.force_login(person.user)

    query = """
      query ($id: ID!, $lang: String!) @locale(lang: $lang) @workflow(state: DRAFT) {
        action(id: $id) {
          name
          relatedActions {
            id
          }
        }
      }
    """
    data = graphql_client_query_data(
        query,
        variables={'id': action.id, 'lang': 'en'},
    )
    assert data['action']['name'] == DRAFT_ACTION_NAME


def test_no_directive_returns_published(
    graphql_client_query_data,
    query_single_action_no_directive,
    action_with_draft,
    person,
    client,
):
    action, published_name = action_with_draft
    plan = action.plan
    person.general_admin_plans.add(plan)
    person.save()
    client.force_login(person.user)

    data = graphql_client_query_data(
        query_single_action_no_directive,
        variables={'id': action.id, 'lang': 'en'},
    )
    assert data['action']['name'] == published_name
