from __future__ import annotations

import re
from typing import TYPE_CHECKING

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest

from actions.models.action import ActionChangeLogMessage, CategoryChangeLogMessage, IndicatorChangeLogMessage
from actions.tests.action_admin_helpers import make_contact_person
from actions.tests.factories import ActionFactory, CategoryFactory, CategoryTypeFactory, PlanFactory
from actions.tests.test_change_log_graphql import (
    get_action_create_url,
    get_action_edit_url,
    get_minimal_action_post_data,
    make_plan_admin,
    submit_change_log_message,
)
from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory

if TYPE_CHECKING:
    from django.test import Client

    from actions.models import Action, Plan
    from users.models import User

pytestmark = pytest.mark.django_db

TAB_HEADING = 'Change history messages'
PUBLIC_BADGE = 'Shown on the public site'
PENDING_BADGE = 'Not yet published'
ADD_UNAVAILABLE_TEXT = 'To add a change history message, save the action, or submit its changes for moderation.'


def message_rows(html: str) -> dict[str, str]:
    """Map each listed message's text to the HTML of its table row."""
    rows = re.findall(r'<tr>(.*?)</tr>', html, flags=re.DOTALL)
    result = {}
    for row in rows:
        match = re.search(r'<div class="change-log-message-content"[^>]*>(.*?)</div>', row, flags=re.DOTALL)
        if match:
            result[match.group(1)] = row
    return result


@pytest.fixture
def plan() -> Plan:
    plan = PlanFactory.create()
    plan.features.enable_change_log = True
    plan.features.save()
    return plan


@pytest.fixture
def admin_user(plan: Plan) -> User:
    return make_plan_admin(plan)


@pytest.fixture
def action(plan: Plan) -> Action:
    action = ActionFactory.create(plan=plan)
    # Saving in the admin creates a revision, which a change history message is tied to
    action.save_revision()
    return action


def create_message(action: Action, content: str, user: User | None = None) -> ActionChangeLogMessage:
    return ActionChangeLogMessage.objects.create(action=action, plan=action.plan, content=content, created_by=user)


def add_message_from_tab(client: Client, action: Action, content: str) -> None:
    """Follow the tab's add link and submit the form it leads to."""
    page = client.get(get_action_edit_url(action.pk)).content.decode().replace('&amp;', '&')
    add_url = re.search(r'href="([^"]*actionchangelogmessage/add/[^"]*)"', page)
    assert add_url is not None
    form_response = client.get(add_url.group(1))
    assert form_response.status_code == 200
    hidden = dict(re.findall(r'<input\s+type="hidden"\s+name="([^"]+)"\s+value="([^"]*)"', form_response.content.decode()))
    response = client.post(reverse('wagtailsnippets_actions_actionchangelogmessage:add'), data={**hidden, 'content': content})
    assert response.status_code == 302


def confirm_deletion(client: Client, delete_url: str):
    """Open the delete link and submit the confirmation form it shows, as the browser does."""
    confirmation = client.get(delete_url).content.decode().replace('&amp;', '&')
    form_action = re.search(r'<form action="([^"]*/delete/[^"]*)" method="POST">', confirmation)
    assert form_action is not None
    return client.post(form_action.group(1))


class TestActionTab:
    def test_lists_messages_newest_first_with_author(self, client: Client, admin_user: User, action: Action):
        create_message(action, 'First message', admin_user)
        create_message(action, 'Second message', admin_user)
        client.force_login(admin_user)

        content = client.get(get_action_edit_url(action.pk)).content.decode()

        assert TAB_HEADING in content
        assert content.index('Second message') < content.index('First message')
        assert admin_user.get_full_name() in message_rows(content)['First message']

    def test_has_edit_delete_and_add_links(self, client: Client, admin_user: User, action: Action):
        message = create_message(action, 'Message')
        client.force_login(admin_user)

        content = client.get(get_action_edit_url(action.pk)).content.decode()

        row = message_rows(content)['Message']
        assert reverse('wagtailsnippets_actions_actionchangelogmessage:edit', args=[message.pk]) in row
        assert reverse('wagtailsnippets_actions_actionchangelogmessage:delete', args=[message.pk]) in row
        add_url = reverse('wagtailsnippets_actions_actionchangelogmessage:add') + f'?action={action.pk}'
        assert add_url in content.replace('&amp;', '&')

    def test_empty_tab_offers_adding(self, client: Client, admin_user: User, action: Action):
        client.force_login(admin_user)

        content = client.get(get_action_edit_url(action.pk)).content.decode()

        assert 'No change history messages have been written yet.' in content
        assert reverse('wagtailsnippets_actions_actionchangelogmessage:add') in content

    def test_no_adding_for_action_without_revisions(self, client: Client, plan: Plan, admin_user: User):
        # Actions created outside the admin, e.g. through the REST API, have no revision to tie a message to
        action = ActionFactory.create(plan=plan)
        client.force_login(admin_user)

        content = client.get(get_action_edit_url(action.pk)).content.decode()

        assert 'actionchangelogmessage/add/' not in content
        assert ADD_UNAVAILABLE_TEXT in content

    def test_hidden_when_change_log_disabled(self, client: Client, plan: Plan, admin_user: User, action: Action):
        plan.features.enable_change_log = False
        plan.features.save()
        create_message(action, 'Old message')
        client.force_login(admin_user)

        content = client.get(get_action_edit_url(action.pk)).content.decode()

        assert TAB_HEADING not in content
        assert 'Old message' not in content

    def test_hidden_on_create_page(self, client: Client, admin_user: User):
        client.force_login(admin_user)

        content = client.get(get_action_create_url()).content.decode()

        assert TAB_HEADING not in content

    def test_query_count_does_not_grow_with_messages(self, client: Client, admin_user: User, action: Action):
        client.force_login(admin_user)
        create_message(action, 'Message 0', admin_user)
        # The first request does one-off work, like creating the avatar's image rendition
        client.get(get_action_edit_url(action.pk))
        with CaptureQueriesContext(connection) as one_message:
            client.get(get_action_edit_url(action.pk))
        for i in range(1, 5):
            create_message(action, f'Message {i}', admin_user)
        with CaptureQueriesContext(connection) as five_messages:
            client.get(get_action_edit_url(action.pk))

        assert len(five_messages) == len(one_message)

    def test_delete_returns_to_edit_page(self, client: Client, admin_user: User, action: Action):
        create_message(action, 'Message')
        client.force_login(admin_user)
        edit_url = get_action_edit_url(action.pk)
        content = client.get(edit_url).content.decode().replace('&amp;', '&')
        delete_url = re.search(r'href="([^"]*actionchangelogmessage/delete/[^"]*)"', content)
        assert delete_url is not None

        response = confirm_deletion(client, delete_url.group(1))

        assert response.status_code == 302
        assert response['Location'] == edit_url
        assert not ActionChangeLogMessage.objects.filter(action=action).exists()


class TestActionStatusWithoutModeration:
    def test_latest_message_is_public(self, client: Client, plan: Plan, admin_user: User):
        client.force_login(admin_user)
        response = client.post(get_action_create_url(), data=get_minimal_action_post_data())
        submit_change_log_message(client, response, 'Created')
        action = plan.actions.get()
        response = client.post(
            get_action_edit_url(action.pk), data=get_minimal_action_post_data(identifier=action.identifier, name='Renamed')
        )
        submit_change_log_message(client, response, 'Renamed')

        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())

        assert PUBLIC_BADGE in rows['Renamed']
        assert PUBLIC_BADGE not in rows['Created']
        assert PENDING_BADGE not in rows['Created'] + rows['Renamed']

    def test_message_added_from_tab_for_new_action_is_public(self, client: Client, plan: Plan, admin_user: User):
        client.force_login(admin_user)
        client.post(get_action_create_url(), data=get_minimal_action_post_data())
        action = plan.actions.get()

        add_message_from_tab(client, action, 'From tab')

        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())
        assert PUBLIC_BADGE in rows['From tab']

    def test_message_added_from_tab_after_edit_is_public(self, client: Client, plan: Plan, admin_user: User):
        client.force_login(admin_user)
        client.post(get_action_create_url(), data=get_minimal_action_post_data())
        action = plan.actions.get()
        client.post(
            get_action_edit_url(action.pk), data=get_minimal_action_post_data(identifier=action.identifier, name='Renamed')
        )

        add_message_from_tab(client, action, 'From tab')

        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())
        assert PUBLIC_BADGE in rows['From tab']

    def test_messages_of_unpublished_action_are_not_pending(self, client: Client, plan: Plan, admin_user: User):
        client.force_login(admin_user)
        response = client.post(get_action_create_url(), data=get_minimal_action_post_data())
        submit_change_log_message(client, response, 'Created')
        action = plan.actions.get()

        action.unpublish()

        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())
        assert PENDING_BADGE not in rows['Created']


class TestActionStatusWithModeration:
    @pytest.fixture(autouse=True)
    def _setup(self, client: Client, plan: Plan, admin_user: User, workflow_factory):
        from django.contrib.auth.models import Group
        from wagtail.models import GroupApprovalTask, WorkflowTask

        workflow = workflow_factory()
        group, _ = Group.objects.get_or_create(name='Moderators')
        approval_task = GroupApprovalTask.objects.create(name='Approve action')
        approval_task.groups.add(group)  # type: ignore[attr-defined]
        WorkflowTask.objects.create(workflow=workflow, task=approval_task, sort_order=0)  # type: ignore[attr-defined]
        plan.features.moderation_workflow = workflow
        plan.features.save()
        admin_user.groups.add(group)
        client.force_login(admin_user)

    def submit(self, client: Client, action: Action, message: str):
        data = get_minimal_action_post_data(identifier=action.identifier, name=action.name)
        data['action-submit'] = 'true'
        response = client.post(get_action_edit_url(action.pk), data=data)
        submit_change_log_message(client, response, message)

    def approve(self, client: Client, action: Action):
        data = get_minimal_action_post_data(identifier=action.identifier, name=action.name)
        data['action-workflow-action'] = 'true'
        data['workflow-action-name'] = 'approve'
        assert client.post(get_action_edit_url(action.pk), data=data).status_code == 302

    def test_message_added_from_tab_for_published_action_is_public(self, client: Client, plan: Plan):
        client.post(get_action_create_url(), data=get_minimal_action_post_data())
        action = plan.actions.get()
        self.submit(client, action, 'Submitted')
        self.approve(client, action)

        add_message_from_tab(client, action, 'From tab')

        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())
        assert PUBLIC_BADGE in rows['From tab']

    def test_no_adding_from_tab_for_unsubmitted_draft(self, client: Client, plan: Plan):
        client.post(get_action_create_url(), data=get_minimal_action_post_data())
        action = plan.actions.get()
        self.submit(client, action, 'Submitted')
        self.approve(client, action)
        # Saving without submitting keeps the changes as a draft, and submitting them will save a new revision
        client.post(get_action_edit_url(action.pk), data=get_minimal_action_post_data(identifier=action.identifier, name='Draft'))

        content = client.get(get_action_edit_url(action.pk)).content.decode()

        assert 'actionchangelogmessage/add/' not in content
        assert ADD_UNAVAILABLE_TEXT in content

    def test_message_added_from_tab_for_submitted_changes_is_pending_until_published(self, client: Client, plan: Plan):
        client.post(get_action_create_url(), data=get_minimal_action_post_data())
        action = plan.actions.get()
        self.submit(client, action, 'Submitted')

        add_message_from_tab(client, action, 'From tab')

        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())
        assert PENDING_BADGE in rows['From tab']
        self.approve(client, action)
        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())
        assert PUBLIC_BADGE in rows['From tab']

    def publish_with_message(self, client: Client, plan: Plan, message: str) -> Action:
        client.post(get_action_create_url(), data=get_minimal_action_post_data())
        action = plan.actions.get()
        self.submit(client, action, message)
        self.approve(client, action)
        action.refresh_from_db()
        return action

    def test_editor_cannot_write_text_shown_without_approval(self, client: Client, plan: Plan):
        plan.features.has_action_contact_person_roles = True
        plan.features.save()
        action = self.publish_with_message(client, plan, 'Approved')
        message = ActionChangeLogMessage.objects.get(action=action)
        client.force_login(make_contact_person(action))

        content = client.get(get_action_edit_url(action.pk)).content.decode()
        assert 'actionchangelogmessage/add/' not in content
        assert 'actionchangelogmessage/edit/' not in message_rows(content)['Approved']

        # Wagtail answers a denied permission with a redirect to the dashboard
        denied = reverse('wagtailadmin_home')
        add_url = reverse('wagtailsnippets_actions_actionchangelogmessage:add')
        revision_id = action.get_public_change_log_revision_id()
        add_data = {'action': action.pk, 'revision': revision_id, 'content': 'New'}
        assert client.post(add_url, data=add_data)['Location'] == denied
        edit_url = reverse('wagtailsnippets_actions_actionchangelogmessage:edit', args=[message.pk])
        assert client.post(edit_url, data={'content': 'Changed'})['Location'] == denied
        delete_url = reverse('wagtailsnippets_actions_actionchangelogmessage:delete', args=[message.pk])
        assert client.post(delete_url)['Location'] == denied
        assert list(ActionChangeLogMessage.objects.filter(action=action).values_list('content', flat=True)) == ['Approved']

    def test_editor_can_write_message_for_submitted_changes(self, client: Client, plan: Plan):
        plan.features.has_action_contact_person_roles = True
        plan.features.save()
        action = self.publish_with_message(client, plan, 'Approved')
        self.submit(client, action, 'Submitted again')
        client.force_login(make_contact_person(action))

        add_message_from_tab(client, action, 'From editor')

        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())
        assert PENDING_BADGE in rows['From editor']
        assert 'actionchangelogmessage/edit/' in rows['From editor']

    def test_query_count_for_editor_does_not_grow_with_messages(self, client: Client, plan: Plan):
        plan.features.has_action_contact_person_roles = True
        plan.features.save()
        action = self.publish_with_message(client, plan, 'Approved')
        self.submit(client, action, 'Submitted again')
        action.refresh_from_db()
        client.force_login(make_contact_person(action))
        client.get(get_action_edit_url(action.pk))
        with CaptureQueriesContext(connection) as before:
            client.get(get_action_edit_url(action.pk))
        for i in range(4):
            ActionChangeLogMessage.objects.create(
                action=action, plan=plan, content=f'Message {i}', revision_id=action.latest_revision_id
            )
        with CaptureQueriesContext(connection) as after:
            client.get(get_action_edit_url(action.pk))

        assert len(after) == len(before)

    def test_message_resubmitted_after_unpublishing_is_pending(self, client: Client, plan: Plan):
        action = self.publish_with_message(client, plan, 'Approved')
        action.unpublish()
        self.submit(client, action, 'Submitted again')

        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())
        assert PENDING_BADGE in rows['Submitted again']
        assert PENDING_BADGE not in rows['Approved']

    def test_editor_cannot_bulk_delete_messages(self, client: Client, plan: Plan):
        plan.features.has_action_contact_person_roles = True
        plan.features.save()
        action = self.publish_with_message(client, plan, 'Approved')
        message = ActionChangeLogMessage.objects.get(action=action)
        client.force_login(make_contact_person(action))

        bulk_delete_url = reverse('wagtail_bulk_action', args=('actions', 'actionchangelogmessage', 'delete'))
        client.post(f'{bulk_delete_url}?id={message.pk}')

        assert ActionChangeLogMessage.objects.filter(pk=message.pk).exists()

    def test_unpublished_action_with_draft_has_no_public_message(self, client: Client, plan: Plan):
        action = self.publish_with_message(client, plan, 'First')
        self.submit(client, action, 'Second')
        self.approve(client, action)
        action.refresh_from_db()
        action.unpublish()

        # The edit form shows the latest revision, whose content still has a live revision
        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())

        assert PUBLIC_BADGE not in rows['First'] + rows['Second']
        assert PENDING_BADGE not in rows['First'] + rows['Second']

    def test_submitted_message_is_pending_until_published(self, client: Client, plan: Plan):
        client.post(get_action_create_url(), data=get_minimal_action_post_data())
        action = plan.actions.get()
        self.submit(client, action, 'Submitted')

        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())
        assert PENDING_BADGE in rows['Submitted']
        assert PUBLIC_BADGE not in rows['Submitted']

        self.approve(client, action)

        rows = message_rows(client.get(get_action_edit_url(action.pk)).content.decode())
        assert PUBLIC_BADGE in rows['Submitted']
        assert PENDING_BADGE not in rows['Submitted']


def test_indicator_tab_lists_messages(client: Client, plan: Plan, admin_user: User):
    indicator = IndicatorFactory.create(organization=plan.organization, common=None)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    IndicatorChangeLogMessage.objects.create(indicator=indicator, plan=plan, content='Older')
    IndicatorChangeLogMessage.objects.create(indicator=indicator, plan=plan, content='Newer')
    client.force_login(admin_user)

    content = client.get(reverse('wagtailsnippets_indicators_indicator:edit', args=[indicator.pk])).content.decode()

    assert TAB_HEADING in content
    rows = message_rows(content)
    assert PUBLIC_BADGE in rows['Newer']
    assert PUBLIC_BADGE not in rows['Older']
    assert reverse('wagtailsnippets_actions_indicatorchangelogmessage:add') + f'?indicator={indicator.pk}' in content


def test_indicator_tab_leaves_out_messages_of_other_plans(client: Client, plan: Plan, admin_user: User):
    other_plan = PlanFactory.create()
    indicator = IndicatorFactory.create(organization=plan.organization, common=None, plans=[plan, other_plan])
    IndicatorChangeLogMessage.objects.create(indicator=indicator, plan=plan, content='Own plan')
    IndicatorChangeLogMessage.objects.create(indicator=indicator, plan=other_plan, content='Other plan')
    client.force_login(admin_user)

    content = client.get(reverse('wagtailsnippets_indicators_indicator:edit', args=[indicator.pk])).content.decode()

    assert 'Own plan' in content
    assert 'Other plan' not in content


def test_deleting_category_message_returns_to_category(client: Client, plan: Plan, admin_user: User):
    category = CategoryFactory.create(type=CategoryTypeFactory.create(plan=plan))
    CategoryChangeLogMessage.objects.create(category=category, plan=plan, content='Category message')
    client.force_login(admin_user)
    edit_url = reverse('wagtailsnippets_actions_category:edit', args=[category.pk]) + f'?category_type={category.type.pk}'
    content = client.get(edit_url).content.decode().replace('&amp;', '&')
    delete_url = re.search(r'href="([^"]*categorychangelogmessage/delete/[^"]*)"', content)
    assert delete_url is not None

    response = confirm_deletion(client, delete_url.group(1))

    assert response['Location'] == edit_url
    assert not CategoryChangeLogMessage.objects.filter(category=category).exists()


def test_category_tab_lists_messages(client: Client, plan: Plan, admin_user: User):
    category = CategoryFactory.create(type=CategoryTypeFactory.create(plan=plan))
    CategoryChangeLogMessage.objects.create(category=category, plan=plan, content='Category message')
    client.force_login(admin_user)

    url = reverse('wagtailsnippets_actions_category:edit', args=[category.pk]) + f'?category_type={category.type.pk}'
    content = client.get(url).content.decode()

    assert TAB_HEADING in content
    assert PUBLIC_BADGE in message_rows(content)['Category message']
    assert reverse('wagtailsnippets_actions_categorychangelogmessage:add') + f'?category={category.pk}' in content


def test_no_message_for_another_plans_action_after_switching_plans(client: Client, plan: Plan, admin_user: User, action: Action):
    other_plan = PlanFactory.create()
    other_plan.general_admins.add(admin_user.person)
    client.force_login(admin_user)
    # The admin switches to another plan in another tab while the form is open
    admin_user.selected_admin_plan = other_plan
    admin_user.save(update_fields=['selected_admin_plan'])

    add_url = reverse('wagtailsnippets_actions_actionchangelogmessage:add')
    response = client.post(add_url, data={'action': action.pk, 'revision': action.latest_revision_id, 'content': 'Message'})

    # Wagtail answers a denied permission with a redirect to the dashboard
    assert response['Location'] == reverse('wagtailadmin_home')
    assert not ActionChangeLogMessage.objects.filter(action=action).exists()
