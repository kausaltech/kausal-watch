"""The moderation workflow as driven through the action edit view."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.urls import reverse
from wagtail.models import Workflow, WorkflowState

import pytest

from actions.models import ActionContactPerson
from actions.tests import action_admin_helpers as h
from actions.tests.factories import ActionFactory, PlanFactory

if TYPE_CHECKING:
    from actions.models import Action

pytestmark = pytest.mark.django_db

CHANGE_LOG_FORM_URL = reverse('wagtailsnippets_actions_actionchangelogmessage:add')


@pytest.fixture
def plan():
    plan = PlanFactory.create()
    h.enable_moderation(plan)
    return plan


@pytest.fixture
def two_step_plan():
    plan = PlanFactory.create()
    h.enable_moderation(plan, task_count=2)
    return plan


@pytest.fixture
def action(plan):
    return ActionFactory.create(plan=plan, name='Published name')


@pytest.fixture
def editor(action):
    return h.make_contact_person(action)


@pytest.fixture
def moderator(action):
    return h.make_moderator(action)


@pytest.fixture
def plan_admin(action):
    return h.make_plan_admin(action.plan)


def workflow_statuses(action: Action) -> list[str]:
    return [state.status for state in WorkflowState.objects.filter(object_id=str(action.pk)).order_by('pk')]


def menu(client, user, action: Action) -> list[str]:
    client.force_login(user)
    return h.action_menu_names(client.get(h.edit_url(action)))


def submit(client, user, action: Action, name: str = 'Draft name'):
    return h.post_edit(client, user, action, 'submit', name=name)


class TestButtons:
    def test_editor_can_save_and_submit(self, client, action, editor):
        assert menu(client, editor, action) == ['action-save', 'action-submit']

    def test_organization_admin_can_save_and_submit(self, client, action):
        assert menu(client, h.make_organization_admin(action), action) == ['action-save', 'action-submit']

    def test_moderator_can_save_and_publish(self, client, action, moderator):
        assert menu(client, moderator, action) == ['action-save', 'action-publish']

    @pytest.mark.parametrize('make_user', [h.make_plan_admin, h.make_superuser])
    def test_admin_can_save_publish_and_delete(self, client, plan, action, make_user):
        assert menu(client, make_user(plan), action) == ['action-save', 'action-publish', 'action-delete']

    def test_moderator_submits_instead_of_publishing_in_a_two_step_workflow(self, client, two_step_plan):
        action = ActionFactory.create(plan=two_step_plan)

        assert menu(client, h.make_moderator(action), action) == ['action-save', 'action-submit']

    def test_admin_can_also_submit_in_a_two_step_workflow(self, client, two_step_plan):
        action = ActionFactory.create(plan=two_step_plan)

        assert menu(client, h.make_plan_admin(two_step_plan), action) == [
            'action-save',
            'action-publish',
            'action-submit',
            'action-delete',
        ]

    def test_submitter_can_only_cancel_while_in_moderation(self, client, action, editor):
        submit(client, editor, action)

        assert set(menu(client, editor, action)) == {'action-locked', 'action-cancel-workflow'}

    def test_another_editor_sees_only_the_lock_while_in_moderation(self, client, action, editor):
        other_editor = h.make_contact_person(action)
        submit(client, editor, action)

        assert set(menu(client, other_editor, action)) == {'action-locked'}

    def test_moderator_can_approve_or_request_changes_while_in_moderation(self, client, action, editor, moderator):
        submit(client, editor, action)

        assert menu(client, moderator, action) == ['action-save', 'action-cancel-workflow', 'approve', 'reject']

    def test_editor_can_resubmit_or_cancel_after_changes_were_requested(self, client, action, editor, moderator):
        submit(client, editor, action)
        h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix'})

        assert menu(client, editor, action) == ['action-save', 'action-restart-workflow', 'action-cancel-workflow']


class TestSubmitting:
    def test_submit_starts_the_workflow_and_keeps_the_published_action(self, client, action, editor):
        response = submit(client, editor, action)

        assert response.status_code == 302
        assert response['Location'] == h.index_url()
        assert any('submitted for moderation' in message for message in h.message_texts(response))
        assert workflow_statuses(action) == ['in_progress']
        action.refresh_from_db()
        assert action.name == 'Published name'
        assert action.has_unpublished_changes
        assert action.latest_revision.content['name'] == 'Draft name'
        state = action.current_workflow_state
        assert state.requested_by == editor
        assert state.current_task_state.revision == action.latest_revision

    def test_submit_goes_to_the_change_log_form_when_the_plan_has_a_change_log(self, client, plan, action, editor):
        plan.features.enable_change_log = True
        plan.features.save()

        response = submit(client, editor, action)

        action.refresh_from_db()
        assert response['Location'] == f'{CHANGE_LOG_FORM_URL}?action={action.pk}&revision={action.latest_revision.pk}'

    def test_error_is_shown_when_the_workflow_cannot_start(self, client, action, editor):
        with patch.object(Workflow, 'start', side_effect=ValidationError('Cannot start')):
            response = submit(client, editor, action)

        assert response.status_code == 302
        assert response['Location'] == h.edit_url(action)
        assert any('Cannot start' in message for message in h.message_texts(response))
        assert workflow_statuses(action) == []

    def test_submitted_action_is_locked_for_the_editor(self, client, action, editor):
        submit(client, editor, action)

        response = h.post_edit(client, editor, action, name='Edited while locked')

        assert response.status_code == 200
        assert any('locked' in message for message in h.message_texts(response))
        action.refresh_from_db()
        assert action.latest_revision.content['name'] == 'Draft name'

    @pytest.mark.parametrize('make_user', [h.make_moderator, h.plan_admin_for])
    def test_submitted_action_can_be_edited_by_approvers(self, client, action, editor, make_user):
        approver = make_user(action)
        submit(client, editor, action)

        response = h.post_edit(client, approver, action, name='Edited by an approver')

        assert response.status_code == 302
        action.refresh_from_db()
        assert action.latest_revision.content['name'] == 'Edited by an approver'
        assert action.name == 'Published name'
        assert workflow_statuses(action) == ['in_progress']


class TestApproving:
    @pytest.mark.parametrize(
        'make_user',
        [h.make_moderator, h.plan_admin_for, h.superuser_for],
    )
    def test_approval_publishes_the_draft(self, client, action, editor, make_user):
        approver = make_user(action)
        submit(client, editor, action)

        response = h.post_workflow_action(client, approver, action, 'approve')

        assert response.status_code == 302
        assert response['Location'] == h.index_url()
        assert any('approved and published' in message for message in h.message_texts(response))
        assert workflow_statuses(action) == ['approved']
        action.refresh_from_db()
        assert action.name == 'Draft name'
        assert not action.has_unpublished_changes
        assert action.live_revision == action.latest_revision

    def test_editor_cannot_approve(self, client, action, editor):
        submit(client, editor, action)

        h.post_workflow_action(client, editor, action, 'approve')

        assert workflow_statuses(action) == ['in_progress']
        action.refresh_from_db()
        assert action.name == 'Published name'

    def test_first_approval_of_a_two_step_workflow_does_not_publish(self, client, two_step_plan):
        action = ActionFactory.create(plan=two_step_plan, name='Published name')
        moderator = h.make_moderator(action)
        submit(client, h.make_contact_person(action), action)
        first_task = action.current_workflow_task

        h.post_workflow_action(client, moderator, action, 'approve')

        assert workflow_statuses(action) == ['in_progress']
        action.refresh_from_db()
        assert action.name == 'Published name'
        assert action.current_workflow_task != first_task

    def test_second_approval_of_a_two_step_workflow_publishes(self, client, two_step_plan):
        action = ActionFactory.create(plan=two_step_plan, name='Published name')
        plan_admin = h.make_plan_admin(two_step_plan)
        moderator = h.make_moderator(action)
        submit(client, h.make_contact_person(action), action)
        h.post_workflow_action(client, moderator, action, 'approve')

        h.post_workflow_action(client, plan_admin, action, 'approve')

        assert workflow_statuses(action) == ['approved']
        action.refresh_from_db()
        assert action.name == 'Draft name'


class TestRequestingChanges:
    def test_moderator_can_open_the_comment_form(self, client, action, editor, moderator):
        submit(client, editor, action)
        task_state = action.current_workflow_task_state
        client.force_login(moderator)

        response = client.get(h.collect_workflow_action_data_url(action, 'reject', task_state.pk))

        assert response.status_code == 200

    def test_requesting_changes_records_the_comment_and_unlocks_the_action(self, client, action, editor, moderator):
        submit(client, editor, action)

        response = h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix'})

        assert response.status_code == 302
        assert workflow_statuses(action) == ['needs_changes']
        state = action.current_workflow_state
        assert state.current_task_state.status == 'rejected'
        assert state.current_task_state.comment == 'Please fix'
        action.refresh_from_db()
        assert action.name == 'Published name'
        response = h.post_edit(client, editor, action, name='Fixed draft')
        assert response.status_code == 302
        action.refresh_from_db()
        assert action.latest_revision.content['name'] == 'Fixed draft'

    def test_submitting_again_resumes_the_workflow(self, client, action, editor, moderator):
        submit(client, editor, action)
        h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix'})

        response = submit(client, editor, action, name='Fixed draft')

        assert response.status_code == 302
        assert workflow_statuses(action) == ['in_progress']
        action.refresh_from_db()
        assert action.latest_revision.content['name'] == 'Fixed draft'
        assert action.name == 'Published name'

    def test_restarting_cancels_the_workflow_and_starts_a_new_one(self, client, action, editor, moderator):
        submit(client, editor, action)
        h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix'})

        response = h.post_edit(client, editor, action, 'restart-workflow', name='Fixed draft')

        assert response.status_code == 302
        assert workflow_statuses(action) == ['cancelled', 'in_progress']


class TestCancelling:
    def test_editor_can_open_the_confirmation(self, client, action, editor):
        submit(client, editor, action)

        response = client.get(h.confirm_workflow_cancellation_url(action))

        assert response.status_code == 200

    def test_submitter_can_cancel_although_the_action_is_locked(self, client, action, editor):
        submit(client, editor, action)

        response = h.post_edit(client, editor, action, 'cancel-workflow')

        assert any('cancelled' in message for message in h.message_texts(response))
        assert workflow_statuses(action) == ['cancelled']
        response = h.post_edit(client, editor, action, name='Edited after cancelling')
        assert response.status_code == 302
        action.refresh_from_db()
        assert action.latest_revision.content['name'] == 'Edited after cancelling'
        assert action.name == 'Published name'

    def test_another_editor_cannot_cancel(self, client, action, editor):
        submit(client, editor, action)

        h.post_edit(client, h.make_contact_person(action), action, 'cancel-workflow')

        assert workflow_statuses(action) == ['in_progress']


class TestPublishing:
    @pytest.mark.parametrize(
        'make_user',
        [h.make_moderator, h.plan_admin_for, h.superuser_for],
    )
    def test_publish_is_live_at_once(self, client, action, make_user):
        response = h.post_edit(client, make_user(action), action, 'publish', name='New name')

        assert response.status_code == 302
        assert response['Location'] == h.index_url()
        assert any('published' in message for message in h.message_texts(response))
        action.refresh_from_db()
        assert action.name == 'New name'
        assert action.live
        assert not action.has_unpublished_changes
        assert action.live_revision == action.latest_revision
        assert workflow_statuses(action) == []

    def test_publish_includes_an_earlier_draft(self, client, action, editor, plan_admin):
        h.post_edit(client, editor, action, name='Draft name')

        h.post_edit(client, plan_admin, action, 'publish')

        action.refresh_from_db()
        assert action.name == 'Draft name'
        assert not action.has_unpublished_changes

    def test_admin_can_unpublish(self, client, action, plan_admin):
        client.force_login(plan_admin)

        response = client.post(h.unpublish_url(action))

        assert response.status_code == 302
        action.refresh_from_db()
        assert not action.live
        assert action.live_revision is None


class TestContactPersons:
    def test_moderator_removed_after_submitting_cannot_open_the_action(self, client, action, editor, moderator):
        submit(client, editor, action)
        ActionContactPerson.objects.filter(action=action, person=moderator.person).delete()
        client.force_login(moderator)

        response = client.get(h.edit_url(action))

        assert response.status_code == 302
        assert workflow_statuses(action) == ['in_progress']

    def test_editor_has_no_contact_person_fields(self, client, action, editor):
        client.force_login(editor)

        form = client.get(h.edit_url(action)).context['form']

        assert not [name for name in form.formsets if name.startswith('contact_persons')]

    def test_admin_has_contact_person_fields(self, client, action, plan_admin):
        client.force_login(plan_admin)

        form = client.get(h.edit_url(action)).context['form']

        assert {'contact_persons_editor', 'contact_persons_moderator'} <= set(form.formsets)


class TestPublishRights:
    @pytest.mark.parametrize('make_user', [h.make_contact_person, h.make_organization_admin])
    def test_user_without_publish_rights_cannot_publish_by_posting(self, client, action, make_user):
        response = h.post_edit(client, make_user(action), action, 'publish', name='New name')

        assert response.status_code == 302
        action.refresh_from_db()
        assert action.name == 'Published name'
        assert action.latest_revision.content['name'] == 'New name'
        assert action.live_revision is None

    def test_moderator_cannot_publish_by_posting_in_a_two_step_workflow(self, client, two_step_plan):
        action = ActionFactory.create(plan=two_step_plan, name='Published name')

        h.post_edit(client, h.make_moderator(action), action, 'publish', name='New name')

        action.refresh_from_db()
        assert action.name == 'Published name'

    @pytest.mark.parametrize(
        'make_user',
        [
            h.make_contact_person,
            lambda action: h.make_contact_person(ActionFactory.create(plan=action.plan)),
            lambda _action: h.make_contact_person(ActionFactory.create()),
            lambda _action: h.make_plan_admin(PlanFactory.create()),
        ],
        ids=['editor', 'contact_person_of_another_action', 'contact_person_in_another_plan', 'admin_of_another_plan'],
    )
    def test_user_without_publish_rights_cannot_unpublish(self, client, action, make_user):
        client.force_login(make_user(action))

        assert client.get(h.unpublish_url(action)).status_code != 200
        client.post(h.unpublish_url(action))

        action.refresh_from_db()
        assert action.live

    def test_moderator_can_unpublish(self, client, action, moderator):
        client.force_login(moderator)

        client.post(h.unpublish_url(action))

        action.refresh_from_db()
        assert not action.live


class TestModerationStatus:
    def test_side_panel_tells_who_last_published(self, client, action, plan_admin):
        h.post_edit(client, plan_admin, action, 'publish', name='New name')

        panel = h.status_side_panel_text(h.get_edit_page(client, plan_admin, action))

        assert 'Live' in panel
        assert str(plan_admin) in panel or plan_admin.get_full_name() in panel

    def test_editor_sees_the_comment_after_changes_were_requested(self, client, action, editor, moderator):
        submit(client, editor, action)
        h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix the heading'})

        response = h.get_edit_page(client, editor, action)

        assert 'Changes requested' in h.status_side_panel_text(response)
        assert 'Please fix the heading' in response.content.decode()

    def test_side_panel_does_not_mention_locking_without_moderation(self, client):
        action = ActionFactory.create()
        admin = h.make_plan_admin(action.plan)
        h.post_edit(client, admin, action, name='New name')

        panel = h.status_side_panel_text(h.get_edit_page(client, admin, action))

        assert 'Live' in panel
        assert 'Locking' not in panel

    def test_side_panel_offers_no_lock_switch_even_to_a_superuser(self, client, plan, action, editor):
        superuser = h.make_superuser(plan)

        unlocked = h.status_side_panel_text(h.get_edit_page(client, superuser, action))
        submit(client, editor, action)
        in_moderation = h.status_side_panel_text(h.get_edit_page(client, superuser, action))

        assert 'Anyone can edit this action' in unlocked
        assert 'lock it' not in unlocked
        assert 'Locked by workflow' in in_moderation
        assert 'lock it' not in in_moderation

    def test_workflow_history_lists_the_moderation_rounds(self, client, action, editor, moderator):
        submit(client, editor, action)
        h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix the heading'})
        state = action.workflow_states.get()

        history = client.get(h.workflow_history_url(action))
        detail = client.get(h.workflow_history_detail_url(action, state.pk))

        assert history.status_code == 200
        assert detail.status_code == 200
        assert 'Please fix the heading' in detail.content.decode()

    @pytest.mark.parametrize(
        'make_user',
        [
            lambda action: h.make_contact_person(ActionFactory.create(plan=action.plan)),
            lambda _action: h.make_plan_admin(PlanFactory.create()),
        ],
        ids=['contact_person_of_another_action', 'admin_of_another_plan'],
    )
    def test_outsider_cannot_open_the_workflow_history_or_comparison(self, client, action, editor, moderator, make_user):
        h.post_edit(client, editor, action, name='First draft')
        submit(client, editor, action)
        state = action.workflow_states.get()
        first, second = action.revisions.order_by('pk')
        client.force_login(make_user(action))

        for url in (
            h.workflow_history_url(action),
            h.workflow_history_detail_url(action, state.pk),
            h.compare_url(action, first.pk, second.pk),
        ):
            assert client.get(url).status_code != 200

    def test_comparison_shows_what_changed_between_two_drafts(self, client, action, editor):
        h.post_edit(client, editor, action, name='First draft')
        h.post_edit(client, editor, action, name='Second draft')
        first, second = action.revisions.order_by('pk')

        response = client.get(h.compare_url(action, first.pk, second.pk))

        assert response.status_code == 200
        changes = h.table_rows(response)
        assert any(row.startswith('Name') and 'First' in row and 'Second' in row for row in changes)
