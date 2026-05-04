import re

from django.urls import reverse

import pytest

from actions.action_admin import ActionAdmin
from actions.models.action import ActionChangeLogMessage
from actions.tests.factories import PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


CHANGE_LOG_QUERY = """
  query ($id: ID!) {
    action(id: $id) {
      changeLogMessage {
        content
        createdAt
      }
    }
  }
"""


def get_action_create_url():
    admin = ActionAdmin()
    return reverse(admin.url_helper.get_action_url_name('create'))


def get_action_edit_url(action_pk):
    admin = ActionAdmin()
    return reverse(admin.url_helper.get_action_url_name('edit'), kwargs={'instance_pk': action_pk})


def get_minimal_action_post_data(*, identifier='test-1', name='Test Action'):
    return {
        'identifier': identifier,
        'name': name,
        'visibility': 'public',
        'responsible_parties_primary-TOTAL_FORMS': '0',
        'responsible_parties_primary-INITIAL_FORMS': '0',
        'responsible_parties_collaborator-TOTAL_FORMS': '0',
        'responsible_parties_collaborator-INITIAL_FORMS': '0',
        'tasks-TOTAL_FORMS': '0',
        'tasks-INITIAL_FORMS': '0',
        'links-TOTAL_FORMS': '0',
        'links-INITIAL_FORMS': '0',
        'contact_persons_editor-TOTAL_FORMS': '0',
        'contact_persons_editor-INITIAL_FORMS': '0',
        'contact_persons_moderator-TOTAL_FORMS': '0',
        'contact_persons_moderator-INITIAL_FORMS': '0',
    }


def extract_hidden_fields(html):
    """
    Extract hidden input fields from the form HTML.

    Returns a dict of {name: value} for all hidden inputs in the form_content block.
    """
    matches = re.findall(r'<input\s+type="hidden"\s+name="([^"]+)"\s+value="([^"]*)"', html)
    return dict(matches)


def submit_change_log_message(client, redirect_response, content):
    """
    Follow the redirect to the change log form, then POST it.

    Simulates the real browser flow: GET the form page (which renders hidden
    fields like 'action' and 'revision' via the template), then POST with
    those hidden fields plus the user-provided content.
    """
    form_url = redirect_response['Location']
    get_response = client.get(form_url)
    assert get_response.status_code == 200

    hidden_fields = extract_hidden_fields(get_response.content.decode())
    post_data = {**hidden_fields, 'content': content}
    change_log_url = reverse('wagtailsnippets_actions_actionchangelogmessage:add')
    return client.post(change_log_url, data=post_data)


def query_change_log_message(graphql_client_query_data, action_id):
    data = graphql_client_query_data(CHANGE_LOG_QUERY, variables={'id': action_id})
    return data['action']['changeLogMessage']


def make_plan_admin(plan):
    """Create a user who is a general admin for the given plan."""
    user = UserFactory.create()
    PersonFactory.create(user=user, general_admin_plans=[plan])
    ClientPlanFactory.create(plan=plan)
    return user


class TestChangeLogWithoutModeration:
    """
    Test change log messages for plans without moderation workflow.

    Without moderation, Action.save_revision() auto-publishes revisions.
    The admin redirects to the change log form via get_success_url().
    """

    @pytest.fixture(autouse=True)
    def _setup(self, client):
        self.plan = PlanFactory.create()
        self.plan.features.enable_change_log = True
        self.plan.features.save()
        self.user = make_plan_admin(self.plan)
        client.force_login(self.user)
        self.client = client

    def test_new_action_change_log_message_visible_via_graphql(
        self,
        graphql_client_query_data,
    ):
        # Create action via the admin form; save_revision() auto-publishes
        post_data = get_minimal_action_post_data()
        response = self.client.post(get_action_create_url(), data=post_data)
        assert response.status_code == 302

        # The redirect should point to the change log message form
        assert 'actionchangelogmessage' in response['Location']

        message_text = 'Created new action'
        submit_change_log_message(self.client, response, message_text)

        action = self.plan.actions.first()
        assert action is not None
        msg = ActionChangeLogMessage.objects.get(action=action)

        # The message must be linked to the live revision, not left as NULL
        assert msg.revision is not None
        assert msg.revision == action.live_revision

        result = query_change_log_message(graphql_client_query_data, action.id)
        assert result is not None
        assert result['content'] == message_text

    def test_edited_action_change_log_message_visible_via_graphql(
        self,
        graphql_client_query_data,
    ):
        # First create an action via the form
        post_data = get_minimal_action_post_data()
        self.client.post(get_action_create_url(), data=post_data)
        action = self.plan.actions.first()
        assert action is not None

        # Edit via the edit form (default action='edit', no explicit publish button)
        edit_post_data = get_minimal_action_post_data(
            identifier=action.identifier,
            name='Updated Action Name',
        )
        response = self.client.post(get_action_edit_url(action.pk), data=edit_post_data)
        assert response.status_code == 302

        assert 'actionchangelogmessage' in response['Location']

        message_text = 'Updated the action'
        submit_change_log_message(self.client, response, message_text)

        action.refresh_from_db()
        result = query_change_log_message(graphql_client_query_data, action.id)
        assert result is not None
        assert result['content'] == message_text

    def test_no_change_log_message_returns_null(
        self,
        graphql_client_query_data,
    ):
        post_data = get_minimal_action_post_data()
        response = self.client.post(get_action_create_url(), data=post_data)
        assert response.status_code == 302

        # Skip the change log message form — don't submit it
        action = self.plan.actions.first()
        assert action is not None
        result = query_change_log_message(graphql_client_query_data, action.id)
        assert result is None


class TestChangeLogWithModeration:
    """
    Test change log messages for plans with moderation workflow.

    With moderation, the create view saves a draft. The user then submits
    from the edit view (action-submit), which starts the workflow and
    redirects to the change log form. Publishing happens via workflow approval.
    """

    @pytest.fixture(autouse=True)
    def _setup(self, client, workflow_factory):
        from django.contrib.auth.models import Group
        from wagtail.models import GroupApprovalTask, WorkflowTask

        self.plan = PlanFactory.create()
        workflow = workflow_factory()
        # Use GroupApprovalTask so the admin user can approve
        group, _ = Group.objects.get_or_create(name='Moderators')
        approval_task = GroupApprovalTask.objects.create(name='Approve action')
        approval_task.groups.add(group)  # type: ignore[attr-defined]
        WorkflowTask.objects.create(workflow=workflow, task=approval_task, sort_order=0)  # type: ignore[attr-defined]
        self.plan.features.enable_change_log = True
        self.plan.features.moderation_workflow = workflow
        self.plan.features.save()
        self.user = make_plan_admin(self.plan)
        self.user.groups.add(group)
        client.force_login(self.user)
        self.client = client

    def _create_action_and_submit_for_moderation(self, message_text):
        """Create an action, then submit it for moderation with a change log message."""
        # Step 1: Create the action (creates draft, no auto-publish)
        post_data = get_minimal_action_post_data()
        create_response = self.client.post(get_action_create_url(), data=post_data)
        assert create_response.status_code == 302
        action = self.plan.actions.first()
        assert action is not None

        # Step 2: Submit for moderation from the edit view
        edit_post_data = get_minimal_action_post_data(
            identifier=action.identifier,
            name=action.name,
        )
        edit_post_data['action-submit'] = 'true'
        submit_response = self.client.post(get_action_edit_url(action.pk), data=edit_post_data)
        assert submit_response.status_code == 302
        assert 'actionchangelogmessage' in submit_response['Location']

        # Step 3: Submit the change log message
        submit_change_log_message(self.client, submit_response, message_text)
        return action

    def test_new_action_message_not_visible_before_publish(
        self,
        graphql_client_query_data,
    ):
        message_text = 'Submitted new action for review'
        action = self._create_action_and_submit_for_moderation(message_text)

        # Before publish, the message should not be visible via GraphQL
        result = query_change_log_message(graphql_client_query_data, action.id)
        assert result is None

    def test_new_action_message_visible_after_publish(
        self,
        graphql_client_query_data,
    ):
        message_text = 'Submitted new action for review'
        action = self._create_action_and_submit_for_moderation(message_text)

        # Approve and publish through the edit form (workflow action)
        approve_post_data = get_minimal_action_post_data(
            identifier=action.identifier,
            name=action.name,
        )
        approve_post_data['action-workflow-action'] = 'true'
        approve_post_data['workflow-action-name'] = 'approve'
        approve_response = self.client.post(get_action_edit_url(action.pk), data=approve_post_data)
        assert approve_response.status_code == 302

        action.refresh_from_db()
        result = query_change_log_message(graphql_client_query_data, action.id)
        assert result is not None
        assert result['content'] == message_text
