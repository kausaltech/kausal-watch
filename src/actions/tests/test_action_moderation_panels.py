"""The moderation panels on the admin front page, and approving an action from them."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import TYPE_CHECKING

from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone
from wagtail.admin.views.home import UserObjectsInWorkflowModerationPanel, WorkflowObjectsToModeratePanel
from wagtail.models import GroupApprovalTask, TaskState, WorkflowState
from wagtail.users.models import UserProfile

import pytest

from actions.models import Action, ActionContactPerson
from actions.models.action import ActionModeratorApprovalTask
from actions.tests import action_admin_helpers as h
from actions.tests.factories import ActionContactFactory, ActionFactory, PlanFactory, WorkflowFactory, WorkflowTaskFactory
from actions.wagtail_hooks import ActionsInModerationPanel, ActionsToModeratePanel
from admin_site.tests.factories import ClientPlanFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.test import Client

    from actions.models import Plan
    from users.models import User

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('moderation_ui')]

HOME_URL = reverse('wagtailadmin_home')

type UserMaker = Callable[[Action], User]

ROLES: dict[str, UserMaker] = {
    'superuser': h.superuser_for,
    'plan_admin': h.plan_admin_for,
    'moderator': h.make_moderator,
    'editor': h.make_contact_person,
    'organization_admin': h.make_organization_admin,
    'contact_person_of_another_action': lambda action: h.make_contact_person(ActionFactory.create(plan=action.plan)),
    'admin_of_another_plan': lambda _action: h.make_plan_admin(PlanFactory.create()),
}


@pytest.fixture
def plan() -> Plan:
    plan = PlanFactory.create()
    h.enable_moderation(plan)
    return plan


@pytest.fixture
def action(plan) -> Action:
    return ActionFactory.create(plan=plan, name='Action in moderation')


@pytest.fixture
def editor(action) -> User:
    return h.make_contact_person(action)


def submit(client: Client, user: User, action: Action) -> TaskState:
    h.post_edit(client, user, action, 'submit', name=action.name)
    state = WorkflowState.objects.get(object_id=str(action.pk), status=WorkflowState.STATUS_IN_PROGRESS)
    assert state.current_task_state is not None
    return state.current_task_state


def select_plan(user: User, plan: Plan) -> User:
    user.selected_admin_plan = plan
    user.save(update_fields=['selected_admin_plan'])
    return user


def home_panels(client: Client, user: User) -> dict[str, str]:
    """Return the rendered moderation panels of the user's front page, by panel name."""
    client.force_login(user)
    response = client.get(HOME_URL)
    assert response.status_code == 200
    return {
        panel.name: panel.render_html({'request': response.wsgi_request, 'csrf_token': response.context['csrf_token']})
        for panel in response.context['panels']
        if isinstance(panel, WorkflowObjectsToModeratePanel | UserObjectsInWorkflowModerationPanel)
    }


def review_panel(client: Client, user: User) -> str:
    return home_panels(client, user).get(WorkflowObjectsToModeratePanel.name, '')


def submissions_panel(client: Client, user: User) -> str:
    return home_panels(client, user).get(UserObjectsInWorkflowModerationPanel.name, '')


def moderatable_actions(user: User) -> set[str]:
    task_states = TaskState.objects.none()
    for task in ActionModeratorApprovalTask.objects.all():
        task_states |= task.get_task_states_user_can_moderate(user)
    return set(WorkflowState.objects.filter(task_states__in=task_states).values_list('object_id', flat=True))


def plan_labels(html: str) -> list[str]:
    """Return the plan labels next to the row titles, in order."""
    return [
        ' '.join(label.split()) for label in re.findall(r'<span class="w-status w-status--label">(.*?)</span>', html, re.DOTALL)
    ]


def is_overdue(html: str) -> bool:
    return bool(re.search(r'<span class="w-status w-status--primary">\s*Overdue\s*</span>', html))


def wait(task_state: TaskState, days: int) -> None:
    TaskState.objects.filter(pk=task_state.pk).update(started_at=timezone.now() - timedelta(days=days))


def plan_with_group_approval(group: Group) -> Plan:
    plan = PlanFactory.create()
    ClientPlanFactory.create(plan=plan)
    group_task = GroupApprovalTask(name='Group approval', active=True)
    group_task.save()
    group_task.groups.add(group)
    workflow = WorkflowFactory.create()
    WorkflowTaskFactory.create(workflow=workflow, task=group_task, sort_order=0)
    plan.features.moderation_workflow = workflow
    plan.features.has_action_contact_person_roles = True
    plan.features.save()
    return plan


def workflow_action_url(action: Action, name: str, task_state: TaskState) -> str:
    return reverse('wagtailsnippets_actions_action:workflow_action', args=[action.pk, name, task_state.pk])


class TestModeratableTaskStates:
    @pytest.mark.parametrize('has_roles', [True, False], ids=['with_roles', 'without_roles'])
    @pytest.mark.parametrize('role', list(ROLES))
    def test_follow_the_approval_rule(self, client, plan, action, role, has_roles):
        plan.features.has_action_contact_person_roles = has_roles
        plan.features.save()
        submit(client, h.make_plan_admin(plan), action)
        user = ROLES[role](action)

        assert moderatable_actions(user) == ({str(action.pk)} if user.can_approve_action(action) else set())

    def test_leave_out_actions_of_another_plan_sharing_the_workflow(self, client, plan, action):
        other_plan = PlanFactory.create()
        other_plan.features.moderation_workflow = plan.features.moderation_workflow
        other_plan.features.has_action_contact_person_roles = True
        other_plan.features.save()
        other_action = ActionFactory.create(plan=other_plan)
        submit(client, h.make_plan_admin(plan), action)
        submit(client, h.make_plan_admin(other_plan), other_action)

        assert moderatable_actions(h.make_plan_admin(plan)) == {str(action.pk)}
        assert moderatable_actions(h.make_moderator(other_action)) == {str(other_action.pk)}

    def test_include_all_plans_of_the_user(self, client, plan, action, editor):
        other_plan = PlanFactory.create()
        h.enable_moderation(other_plan)
        other_action = ActionFactory.create(plan=other_plan)
        submit(client, editor, action)
        submit(client, h.make_contact_person(other_action), other_action)
        admin = UserFactory.create(selected_admin_plan=plan)
        PersonFactory.create(user=admin, general_admin_plans=[plan, other_plan])

        assert moderatable_actions(admin) == {str(action.pk), str(other_action.pk)}

    def test_give_a_superuser_only_the_active_plan_and_their_own_plans(self, client, plan, action, editor):
        other_plan = PlanFactory.create()
        h.enable_moderation(other_plan)
        other_action = ActionFactory.create(plan=other_plan)
        submit(client, editor, action)
        submit(client, h.make_contact_person(other_action), other_action)

        assert moderatable_actions(h.make_superuser(plan)) == {str(action.pk)}


class TestReviewPanel:
    def test_moderator_sees_the_submitted_action(self, client, action, editor):
        submit(client, editor, action)

        assert 'Action in moderation' in review_panel(client, h.make_moderator(action))

    def test_editor_does_not_see_the_action_to_review(self, client, action, editor):
        submit(client, editor, action)

        assert 'Action in moderation' not in review_panel(client, h.make_contact_person(action))

    def test_superuser_sees_only_the_active_plan(self, client, plan, action, editor):
        other_plan = PlanFactory.create()
        h.enable_moderation(other_plan)
        other_action = ActionFactory.create(plan=other_plan, name='Action of another plan')
        submit(client, editor, action)
        submit(client, h.make_contact_person(other_action), other_action)

        html = review_panel(client, h.make_superuser(plan))

        assert 'Action in moderation' in html
        assert 'Action of another plan' not in html

    def test_group_approval_task_of_another_plan_is_left_out(self, client, plan, action, editor):
        other_plan = PlanFactory.create()
        ClientPlanFactory.create(plan=other_plan)
        group_task = GroupApprovalTask(name='Group approval', active=True)
        group_task.save()
        group_task.groups.add(Group.objects.create(name='Approvers'))
        workflow = WorkflowFactory.create()
        WorkflowTaskFactory.create(workflow=workflow, task=group_task, sort_order=0)
        other_plan.features.moderation_workflow = workflow
        other_plan.features.has_action_contact_person_roles = True
        other_plan.features.save()
        other_action = ActionFactory.create(plan=other_plan, name='Action of another plan')
        submit(client, editor, action)
        submit(client, h.make_contact_person(other_action), other_action)

        html = review_panel(client, h.make_superuser(plan))

        assert 'Action in moderation' in html
        assert 'Action of another plan' not in html

    def test_lists_the_actions_of_all_the_users_plans_with_the_active_plan_first(self, client, plan, action, editor):
        plan.name = 'Sunnyside'
        plan.save(update_fields=['name'])
        other_plan = PlanFactory.create(name='Rainyside')
        h.enable_moderation(other_plan)
        ClientPlanFactory.create(plan=other_plan)
        other_action = ActionFactory.create(plan=other_plan, name='Action of another plan')
        moderator = h.make_moderator(action)
        ActionContactFactory.create(action=other_action, person=moderator.person, role=ActionContactPerson.Role.MODERATOR)
        submit(client, h.make_contact_person(other_action), other_action)
        submit(client, editor, action)

        html = review_panel(client, select_plan(moderator, plan))

        assert plan_labels(html) == ['Sunnyside', 'Rainyside']
        assert html.index('Action in moderation') < html.index('Action of another plan')

    def test_rows_of_other_plans_link_to_the_action_and_its_comparison(self, client, plan, action, editor):
        other_plan = PlanFactory.create()
        h.enable_moderation(other_plan)
        ClientPlanFactory.create(plan=other_plan)
        other_action = ActionFactory.create(plan=other_plan)
        moderator = h.make_moderator(action)
        ActionContactFactory.create(action=other_action, person=moderator.person, role=ActionContactPerson.Role.MODERATOR)
        submit(client, h.make_contact_person(other_action), other_action)

        html = review_panel(client, select_plan(moderator, plan))

        assert f'href="{h.edit_url(other_action)}"' in html
        other_action.refresh_from_db()
        assert other_action.latest_revision is not None
        response = client.get(h.compare_url(other_action, 'live', other_action.latest_revision.pk))
        assert response.status_code == 302
        assert response['Location'].startswith(reverse('change-admin-plan', kwargs={'plan_id': other_plan.pk}))

    def test_names_no_plan_when_all_actions_are_in_one_plan(self, client, plan, action, editor):
        submit(client, editor, action)

        assert plan_labels(review_panel(client, h.make_moderator(action))) == []

    def test_shows_no_progress_for_a_single_step_workflow(self, client, action, editor):
        submit(client, editor, action)

        assert '#icon-radio-empty' not in review_panel(client, h.make_moderator(action))

    def test_shows_the_progress_of_a_multi_step_workflow(self, client):
        plan = PlanFactory.create()
        h.enable_moderation(plan, task_count=2)
        action = ActionFactory.create(plan=plan)
        submit(client, h.make_contact_person(action), action)

        html = review_panel(client, h.make_moderator(action))

        assert html.count('#icon-radio-empty') == 2

    def test_group_member_without_a_role_in_the_plan_does_not_see_its_actions(self, client, plan):
        group = Group.objects.create(name='Approvers')
        other_action = ActionFactory.create(plan=plan_with_group_approval(group), name='Action of another plan')
        submit(client, h.make_contact_person(other_action), other_action)
        admin_of_this_plan = h.make_plan_admin(plan)
        admin_of_this_plan.groups.add(group)

        assert 'Action of another plan' not in review_panel(client, admin_of_this_plan)

    def test_offers_approving_and_requesting_changes(self, client, action, editor):
        task_state = submit(client, editor, action)

        html = review_panel(client, h.make_moderator(action))

        assert workflow_action_url(action, 'approve', task_state) in html
        assert workflow_action_url(action, 'reject', task_state) in html


def test_plan_names_are_in_the_admin_language(client, plan, action, editor):
    plan.name = 'Sunnyside'
    plan.name_fi = 'Aurinkoranta'
    plan.save()
    other_plan = PlanFactory.create()
    h.enable_moderation(other_plan)
    ClientPlanFactory.create(plan=other_plan)
    other_action = ActionFactory.create(plan=other_plan)
    moderator = h.make_moderator(action)
    ActionContactFactory.create(action=other_action, person=moderator.person, role=ActionContactPerson.Role.MODERATOR)
    submit(client, h.make_contact_person(other_action), other_action)
    submit(client, editor, action)
    profile = UserProfile.get_for_user(moderator)
    profile.preferred_language = 'fi'
    profile.save()

    html = review_panel(client, select_plan(moderator, plan))

    assert plan_labels(html)[0] == 'Aurinkoranta'
    assert 'Sunnyside' not in html


class TestSubmissionsPanel:
    def test_shows_when_changes_were_requested(self, client, action, editor):
        moderator = h.make_moderator(action)
        submit(client, editor, action)
        h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix the name'})

        assert 'Changes requested at' in submissions_panel(client, editor)

    def test_heading_speaks_of_submissions(self, client, action, editor):
        submit(client, editor, action)

        html = submissions_panel(client, editor)

        assert '<span data-panel-heading-text>Your submissions in moderation</span>' in html
        assert 'pages and snippets' not in html

    def test_submitter_sees_the_submitted_action(self, client, action, editor):
        submit(client, editor, action)

        assert 'Action in moderation' in submissions_panel(client, editor)

    def test_submissions_in_all_plans_are_listed_with_the_active_plan_first(self, client, plan, action, editor):
        other_plan = PlanFactory.create()
        h.enable_moderation(other_plan)
        ClientPlanFactory.create(plan=other_plan)
        other_action = ActionFactory.create(plan=other_plan, name='Action of another plan')
        ActionContactFactory.create(action=other_action, person=editor.person, role=ActionContactPerson.Role.EDITOR)
        submit(client, editor, other_action)
        submit(client, select_plan(editor, plan), action)

        html = submissions_panel(client, select_plan(editor, plan))

        assert plan_labels(html) == [plan.name, other_plan.name]
        assert html.index('Action in moderation') < html.index('Action of another plan')


def test_panels_come_first_on_the_front_page(client, action, editor):
    submit(client, editor, action)
    client.force_login(h.make_moderator(action))

    panels = client.get(HOME_URL).context['panels']

    assert [type(panel) for panel in panels[:2]] == [ActionsToModeratePanel, ActionsInModerationPanel]


def test_panels_are_hidden_unless_the_moderation_ui_is_enabled(client, settings, action, editor):
    settings.ENABLE_ACTION_MODERATION_UI = False
    submit(client, editor, action)

    assert home_panels(client, h.make_moderator(action)) == {}
    assert home_panels(client, editor) == {}


def test_panels_show_nothing_without_actions_in_moderation(client):
    action = ActionFactory.create(plan=PlanFactory.create())

    assert not any(html.strip() for html in home_panels(client, h.plan_admin_for(action)).values())


class TestApprovingFromThePanel:
    def test_moderator_approves(self, client, action, editor):
        task_state = submit(client, editor, action)
        client.force_login(h.make_moderator(action))

        client.post(workflow_action_url(action, 'approve', task_state))

        task_state.refresh_from_db()
        assert task_state.status == TaskState.STATUS_APPROVED

    def test_editor_cannot_approve(self, client, action, editor):
        task_state = submit(client, editor, action)
        client.force_login(h.make_contact_person(action))

        response = client.post(workflow_action_url(action, 'approve', task_state))

        assert response.status_code == 302
        assert response['Location'] == HOME_URL
        task_state.refresh_from_db()
        assert task_state.status == TaskState.STATUS_IN_PROGRESS

    def test_task_state_of_another_action_is_refused(self, client, plan, action, editor):
        other_action = ActionFactory.create(plan=plan)
        submit(client, editor, action)
        other_task_state = submit(client, h.make_contact_person(other_action), other_action)
        client.force_login(h.make_moderator(action))

        response = client.post(workflow_action_url(action, 'approve', other_task_state))

        assert response.status_code == 404
        other_task_state.refresh_from_db()
        assert other_task_state.status == TaskState.STATUS_IN_PROGRESS

    def test_admin_of_two_plans_approves_outside_the_active_plan(self, client, plan, action, editor):
        task_state = submit(client, editor, action)
        other_plan = PlanFactory.create()
        ClientPlanFactory.create(plan=other_plan)
        admin = UserFactory.create(selected_admin_plan=other_plan)
        PersonFactory.create(user=admin, general_admin_plans=[plan, other_plan])
        client.force_login(admin)

        client.post(workflow_action_url(action, 'approve', task_state))

        task_state.refresh_from_db()
        assert task_state.status == TaskState.STATUS_APPROVED

    def test_group_member_without_a_role_in_the_plan_cannot_approve(self, client, plan):
        group = Group.objects.create(name='Approvers')
        other_action = ActionFactory.create(plan=plan_with_group_approval(group))
        task_state = submit(client, h.make_contact_person(other_action), other_action)
        admin_of_this_plan = h.make_plan_admin(plan)
        admin_of_this_plan.groups.add(group)
        client.force_login(admin_of_this_plan)

        client.post(workflow_action_url(other_action, 'approve', task_state))

        task_state.refresh_from_db()
        assert task_state.status == TaskState.STATUS_IN_PROGRESS

    def test_admin_of_another_plan_cannot_approve(self, client, action, editor):
        task_state = submit(client, editor, action)
        client.force_login(h.make_plan_admin(PlanFactory.create()))

        client.post(workflow_action_url(action, 'approve', task_state))

        task_state.refresh_from_db()
        assert task_state.status == TaskState.STATUS_IN_PROGRESS


def test_lists_the_longest_waiting_first(client, plan, action, editor):
    other_action = ActionFactory.create(plan=plan, name='Waiting longer')
    moderator = h.make_moderator(action)
    ActionContactFactory.create(action=other_action, person=moderator.person, role=ActionContactPerson.Role.MODERATOR)
    ActionContactFactory.create(action=other_action, person=editor.person, role=ActionContactPerson.Role.EDITOR)
    submit(client, editor, action)
    wait(submit(client, editor, other_action), 3)

    for html in (review_panel(client, moderator), submissions_panel(client, editor)):
        assert html.index('Waiting longer') < html.index('Action in moderation')


def test_groups_the_other_plans_by_name(client, plan, action, editor):
    moderator = h.make_moderator(action)
    other_plans = {}
    for name in ('Zeta plan', 'Alpha plan'):
        other_plans[name] = PlanFactory.create(name=name)
        h.enable_moderation(other_plans[name])
        ClientPlanFactory.create(plan=other_plans[name])
    for name, days in [('Zeta plan', 9), ('Alpha plan', 1), ('Zeta plan', 2)]:
        other_action = ActionFactory.create(plan=other_plans[name], name=f'{name} action waiting {days} days')
        ActionContactFactory.create(action=other_action, person=moderator.person, role=ActionContactPerson.Role.MODERATOR)
        wait(submit(client, h.make_contact_person(other_action), other_action), days)
    submit(client, editor, action)

    html = review_panel(client, select_plan(moderator, plan))

    titles = [
        'Action in moderation',
        'Alpha plan action waiting 1 days',
        'Zeta plan action waiting 9 days',
        'Zeta plan action waiting 2 days',
    ]
    positions = [html.index(title) for title in titles]
    assert positions == sorted(positions)


class TestOverdue:
    @pytest.mark.parametrize(('days', 'overdue'), [(13, False), (15, True)])
    def test_review_waiting_more_than_two_weeks_is_overdue(self, client, action, editor, days, overdue):
        wait(submit(client, editor, action), days)

        assert is_overdue(review_panel(client, h.make_moderator(action))) is overdue

    @pytest.mark.parametrize(('days', 'overdue'), [(13, False), (15, True)])
    def test_submission_waiting_more_than_two_weeks_is_overdue(self, client, action, editor, days, overdue):
        wait(submit(client, editor, action), days)

        assert is_overdue(submissions_panel(client, editor)) is overdue

    def test_submission_with_changes_requested_is_not_overdue(self, client, action, editor):
        moderator = h.make_moderator(action)
        task_state = submit(client, editor, action)
        h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix the name'})
        wait(task_state, 30)

        html = submissions_panel(client, editor)

        assert 'Changes requested at' in html
        assert not is_overdue(html)


class TestWorkflowCombinations:
    def test_action_reappears_for_the_second_step_with_its_progress(self, client):
        plan = PlanFactory.create()
        h.enable_moderation(plan, task_count=2)
        action = ActionFactory.create(plan=plan, name='Action in moderation')
        editor = h.make_contact_person(action)
        moderator = h.make_moderator(action)
        submit(client, editor, action)

        h.post_workflow_action(client, moderator, action, 'approve')

        html = review_panel(client, h.make_plan_admin(plan))
        assert 'Action in moderation' in html
        assert html.count('#icon-success') == 1
        assert html.count('#icon-radio-empty') == 1

    def test_requesting_changes_from_the_panel_returns_the_action_to_the_submitter(self, client, action, editor):
        moderator = h.make_moderator(action)
        task_state = submit(client, editor, action)
        client.force_login(moderator)

        client.post(workflow_action_url(action, 'reject', task_state), {'comment': 'Please fix the name'})

        task_state.refresh_from_db()
        assert task_state.status == TaskState.STATUS_REJECTED
        assert task_state.get_comment() == 'Please fix the name'
        assert 'Action in moderation' not in review_panel(client, moderator)
        assert 'Changes requested at' in submissions_panel(client, editor)

    def test_cancelled_submission_leaves_both_panels(self, client, action, editor):
        moderator = h.make_moderator(action)
        submit(client, editor, action)

        h.post_edit(client, editor, action, 'cancel-workflow')

        assert 'Action in moderation' not in review_panel(client, moderator)
        assert 'Action in moderation' not in submissions_panel(client, editor)

    def test_resubmitted_action_awaits_review_again(self, client, action, editor):
        moderator = h.make_moderator(action)
        submit(client, editor, action)
        h.post_workflow_action(client, moderator, action, 'reject', {'comment': 'Please fix the name'})

        submit(client, editor, action)

        html = submissions_panel(client, editor)
        assert 'Awaiting' in html
        assert 'Changes requested at' not in html
        assert 'Action in moderation' in review_panel(client, moderator)

    def test_group_member_with_a_role_in_the_plan_sees_and_approves_its_actions(self, client):
        group = Group.objects.create(name='Approvers')
        group_plan = plan_with_group_approval(group)
        action = ActionFactory.create(plan=group_plan, name='Action of the group plan')
        task_state = submit(client, h.make_contact_person(action), action)
        admin = h.make_plan_admin(group_plan)
        admin.groups.add(group)

        assert 'Action of the group plan' in review_panel(client, admin)
        client.post(workflow_action_url(action, 'approve', task_state))
        task_state.refresh_from_db()
        assert task_state.status == TaskState.STATUS_APPROVED

    def test_superuser_also_gets_the_plans_they_administer(self, client, plan, action, editor):
        other_plan = PlanFactory.create()
        h.enable_moderation(other_plan)
        ClientPlanFactory.create(plan=other_plan)
        other_action = ActionFactory.create(plan=other_plan, name='Action of another plan')
        submit(client, h.make_contact_person(other_action), other_action)
        submit(client, editor, action)
        superuser = h.make_superuser(plan)
        PersonFactory.create(user=superuser, general_admin_plans=[other_plan])

        html = review_panel(client, superuser)

        assert 'Action in moderation' in html
        assert 'Action of another plan' in html

    def test_plan_and_overdue_labels_follow_the_title_in_that_order(self, client, plan, action, editor):
        plan.name = 'Sunnyside'
        plan.save(update_fields=['name'])
        other_plan = PlanFactory.create()
        h.enable_moderation(other_plan)
        ClientPlanFactory.create(plan=other_plan)
        other_action = ActionFactory.create(plan=other_plan)
        moderator = h.make_moderator(action)
        ActionContactFactory.create(action=other_action, person=moderator.person, role=ActionContactPerson.Role.MODERATOR)
        submit(client, h.make_contact_person(other_action), other_action)
        wait(submit(client, editor, action), 20)

        html = review_panel(client, select_plan(moderator, plan))

        assert re.search(
            r'Action in moderation</a>\s*<span class="w-status w-status--label">\s*Sunnyside\s*</span>\s*'
            r'<span class="w-status w-status--primary">\s*Overdue\s*</span>',
            html,
        )
