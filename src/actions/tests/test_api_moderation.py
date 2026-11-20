"""
Moderation in the REST endpoints behind the action and task table editors.

These endpoints write the live action, bypassing drafts and the moderation workflow. So they may change an action,
or its tasks, only where the user could publish it in the admin form, and never while it has an unpublished draft.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.urls import reverse

import pytest

from actions.models import Action, ActionContactPerson, ActionTask
from actions.tests.factories import (
    ActionContactFactory,
    ActionFactory,
    ActionResponsiblePartyFactory,
    ActionTaskFactory,
    PlanFactory,
    WorkflowFactory,
    WorkflowTaskFactory,
)
from orgs.tests.factories import OrganizationFactory, OrganizationPlanAdminFactory
from people.tests.factories import PersonFactory
from users.models import ActionReadOnlyReason

if TYPE_CHECKING:
    from collections.abc import Callable

    from actions.models import Plan
    from users.models import User

pytestmark = pytest.mark.django_db


def make_plan(workflow_steps: int) -> Plan:
    """Create a plan with one action and, unless `workflow_steps` is 0, a moderation workflow of that many steps."""
    plan = PlanFactory.create()
    if workflow_steps:
        workflow = WorkflowFactory.create()
        for _ in range(workflow_steps):
            WorkflowTaskFactory.create(workflow=workflow)
        plan.features.moderation_workflow = workflow
    # Without roles, editors would act as moderators
    plan.features.has_action_contact_person_roles = True
    plan.features.save()
    ActionFactory.create(plan=plan)
    return plan


def make_contact(plan: Plan, role: ActionContactPerson.Role) -> User:
    acp = ActionContactFactory.create(action=plan.actions.get(), role=role)
    assert acp.person.user is not None
    return acp.person.user


def make_plan_admin(plan: Plan) -> User:
    person = PersonFactory.create(general_admin_plans=[plan])
    assert person.user is not None
    return person.user


def make_org_admin(plan: Plan) -> User:
    """Make an organization admin, without a contact person role, of the organization responsible for the action."""
    organization = OrganizationFactory.create()
    ActionResponsiblePartyFactory.create(action=plan.actions.get(), organization=organization)
    org_admin = OrganizationPlanAdminFactory.create(plan=plan, organization=organization)
    assert org_admin.person.user is not None
    return org_admin.person.user


def add_draft(plan: Plan) -> None:
    Action.objects.filter(plan=plan).update(has_unpublished_changes=True)


@dataclass
class Situation:
    user: User
    plan: Plan
    action: Action = field(init=False)

    def __post_init__(self):
        self.action = self.plan.actions.get()


def editor_on_moderated_plan() -> Situation:
    plan = make_plan(1)
    return Situation(make_contact(plan, ActionContactPerson.Role.EDITOR), plan)


def moderator_on_one_step_workflow() -> Situation:
    plan = make_plan(1)
    return Situation(make_contact(plan, ActionContactPerson.Role.MODERATOR), plan)


def moderator_on_multi_step_workflow() -> Situation:
    plan = make_plan(2)
    return Situation(make_contact(plan, ActionContactPerson.Role.MODERATOR), plan)


def plan_admin_on_moderated_plan() -> Situation:
    plan = make_plan(1)
    return Situation(make_plan_admin(plan), plan)


def org_admin_on_moderated_plan() -> Situation:
    plan = make_plan(1)
    return Situation(make_org_admin(plan), plan)


def contact_on_unmoderated_plan() -> Situation:
    plan = make_plan(0)
    return Situation(make_contact(plan, ActionContactPerson.Role.EDITOR), plan)


def plan_admin_with_draft() -> Situation:
    situation = plan_admin_on_moderated_plan()
    add_draft(situation.plan)
    situation.action.refresh_from_db()
    return situation


def contact_with_draft_on_unmoderated_plan() -> Situation:
    situation = contact_on_unmoderated_plan()
    add_draft(situation.plan)
    situation.action.refresh_from_db()
    return situation


# Each situation with the reason the user may not edit the action live, or None if they may
SITUATIONS: list[tuple[Callable[[], Situation], ActionReadOnlyReason | None]] = [
    (editor_on_moderated_plan, ActionReadOnlyReason.NEEDS_MODERATION),
    (moderator_on_one_step_workflow, None),
    (moderator_on_multi_step_workflow, ActionReadOnlyReason.NEEDS_MODERATION),
    (plan_admin_on_moderated_plan, None),
    (org_admin_on_moderated_plan, ActionReadOnlyReason.NEEDS_MODERATION),
    (contact_on_unmoderated_plan, None),
    (plan_admin_with_draft, ActionReadOnlyReason.PENDING_DRAFT),
    (contact_with_draft_on_unmoderated_plan, ActionReadOnlyReason.PENDING_DRAFT),
]

situations = pytest.mark.parametrize(('make_situation', 'reason'), SITUATIONS, ids=[s.__name__ for s, _ in SITUATIONS])


def expected_status(reason: ActionReadOnlyReason | None, allowed: int) -> int:
    return allowed if reason is None else 403


def action_detail_url(action: Action) -> str:
    return reverse('action-detail', kwargs={'plan_pk': action.plan_id, 'pk': action.pk})


def action_list_url(plan: Plan) -> str:
    return reverse('action-list', args=(plan.pk,))


def task_detail_url(task: ActionTask) -> str:
    return reverse('action-task-detail', kwargs={'plan_pk': task.action.plan_id, 'pk': task.pk})


def task_list_url(plan: Plan) -> str:
    return reverse('action-task-list', args=(plan.pk,))


def list_rows(response) -> list[dict]:
    assert response.status_code == 200, response.content
    return response.json()['results']


def assert_denied_with(response, reason: ActionReadOnlyReason | None) -> None:
    if reason is None:
        return
    assert response.json()['detail'] == reason.message


@situations
def test_user_rule(make_situation, reason):
    situation = make_situation()
    assert situation.user.get_action_read_only_reason(situation.action) == reason


@situations
def test_action_put(api_client, make_situation, reason):
    s = make_situation()
    api_client.force_login(s.user)
    response = api_client.put(
        action_detail_url(s.action), data={'identifier': s.action.identifier, 'id': s.action.pk, 'name': 'New name'}
    )
    assert response.status_code == expected_status(reason, 200), response.content
    assert_denied_with(response, reason)
    s.action.refresh_from_db()
    assert (s.action.name == 'New name') is (reason is None)


@situations
def test_action_patch(api_client, make_situation, reason):
    s = make_situation()
    api_client.force_login(s.user)
    response = api_client.patch(action_detail_url(s.action), data={'name': 'New name'})
    assert response.status_code == expected_status(reason, 200), response.content
    s.action.refresh_from_db()
    assert (s.action.name == 'New name') is (reason is None)


@situations
def test_action_bulk_put(api_client, make_situation, reason):
    s = make_situation()
    api_client.force_login(s.user)
    response = api_client.put(
        action_list_url(s.plan), data=[{'identifier': s.action.identifier, 'id': s.action.pk, 'name': 'New name'}]
    )
    assert response.status_code == expected_status(reason, 200), response.content
    s.action.refresh_from_db()
    assert (s.action.name == 'New name') is (reason is None)


@situations
def test_task_create(api_client, make_situation, reason):
    s = make_situation()
    api_client.force_login(s.user)
    response = api_client.post(
        task_list_url(s.plan), data={'action': s.action.pk, 'name': 'New task', 'due_at': '2030-01-01', 'state': 'not_started'}
    )
    assert response.status_code == expected_status(reason, 201), response.content
    assert_denied_with(response, reason)
    assert ActionTask.objects.filter(name='New task').exists() is (reason is None)


@situations
def test_task_update(api_client, make_situation, reason):
    s = make_situation()
    task = ActionTaskFactory.create(action=s.action)
    api_client.force_login(s.user)
    response = api_client.patch(task_detail_url(task), data={'name': 'New name'})
    assert response.status_code == expected_status(reason, 200), response.content
    assert_denied_with(response, reason)
    task.refresh_from_db()
    assert (task.name == 'New name') is (reason is None)


@situations
def test_task_bulk_update(api_client, make_situation, reason):
    s = make_situation()
    task = ActionTaskFactory.create(action=s.action)
    api_client.force_login(s.user)
    response = api_client.patch(task_list_url(s.plan), data=[{'id': task.pk, 'name': 'New name'}])
    assert response.status_code == expected_status(reason, 200), response.content
    task.refresh_from_db()
    assert (task.name == 'New name') is (reason is None)


@situations
def test_task_delete(api_client, make_situation, reason):
    s = make_situation()
    task = ActionTaskFactory.create(action=s.action)
    api_client.force_login(s.user)
    response = api_client.delete(task_detail_url(task))
    assert response.status_code == expected_status(reason, 204), response.content
    assert ActionTask.objects.filter(pk=task.pk).exists() is (reason is not None)


@situations
def test_task_move_to_another_action(api_client, make_situation, reason):
    """Moving a task needs the right to edit both actions live."""
    s = make_situation()
    other_action = ActionFactory.create(plan=s.plan)
    if s.action.has_unpublished_changes:
        add_draft(s.plan)  # for the new action too
    for acp in s.action.contact_persons.all():
        ActionContactFactory.create(action=other_action, person=acp.person, role=acp.role)
    for party in s.action.responsible_parties.all():
        ActionResponsiblePartyFactory.create(action=other_action, organization=party.organization)
    task = ActionTaskFactory.create(action=s.action)
    api_client.force_login(s.user)
    response = api_client.patch(task_detail_url(task), data={'action': other_action.pk})
    assert response.status_code == expected_status(reason, 200), response.content
    task.refresh_from_db()
    assert (task.action.pk == other_action.pk) is (reason is None)


@situations
def test_row_flags(api_client, make_situation, reason):
    s = make_situation()
    api_client.force_login(s.user)
    [row] = list_rows(api_client.get(action_list_url(s.plan)))
    assert row['modifiable_by_user'] is (reason is None)
    assert row['read_only_reason'] == (None if reason is None else reason.value)


def test_row_flags_for_an_action_the_user_may_not_modify(api_client):
    plan = make_plan(0)
    user = make_contact(plan, ActionContactPerson.Role.EDITOR)
    other_action = ActionFactory.create(plan=plan)
    api_client.force_login(user)
    rows = {row['id']: row for row in list_rows(api_client.get(action_list_url(plan)))}
    assert rows[other_action.pk]['modifiable_by_user'] is False
    assert rows[other_action.pk]['read_only_reason'] == ActionReadOnlyReason.NOT_PERMITTED.value


@pytest.mark.parametrize('workflow_steps', [0, 1])
def test_task_cannot_be_created_on_another_action(api_client, workflow_steps):
    plan = make_plan(workflow_steps)
    user = make_contact(plan, ActionContactPerson.Role.MODERATOR)
    other_action = ActionFactory.create(plan=plan)
    api_client.force_login(user)
    response = api_client.post(
        task_list_url(plan), data={'action': other_action.pk, 'name': 'New task', 'due_at': '2030-01-01', 'state': 'not_started'}
    )
    assert response.status_code == 403, response.content
    assert not ActionTask.objects.filter(name='New task').exists()


def test_task_cannot_be_moved_to_another_action(api_client):
    plan = make_plan(0)
    user = make_contact(plan, ActionContactPerson.Role.EDITOR)
    task = ActionTaskFactory.create(action=plan.actions.get())
    other_action = ActionFactory.create(plan=plan)
    api_client.force_login(user)
    response = api_client.patch(task_detail_url(task), data={'action': other_action.pk})
    assert response.status_code == 403, response.content
    task.refresh_from_db()
    assert task.action.pk != other_action.pk


def test_task_cannot_be_moved_away_from_a_moderated_action(api_client):
    """The task's current action counts too, not just the one it moves to."""
    plan = make_plan(1)
    user = make_contact(plan, ActionContactPerson.Role.EDITOR)
    task = ActionTaskFactory.create(action=plan.actions.get())
    other_action = ActionFactory.create(plan=plan)
    ActionContactFactory.create(action=other_action, person=user.person, role=ActionContactPerson.Role.MODERATOR)
    api_client.force_login(user)
    response = api_client.patch(task_detail_url(task), data={'action': other_action.pk})
    assert response.status_code == 403, response.content
    task.refresh_from_db()
    assert task.action.pk != other_action.pk


def test_bulk_update_with_a_forbidden_row_writes_nothing(api_client):
    plan = make_plan(1)
    user = make_contact(plan, ActionContactPerson.Role.MODERATOR)
    allowed = plan.actions.get()
    forbidden = ActionFactory.create(plan=plan)
    ActionContactFactory.create(action=forbidden, person=user.person, role=ActionContactPerson.Role.EDITOR)
    api_client.force_login(user)
    response = api_client.put(
        action_list_url(plan),
        data=[
            {'identifier': allowed.identifier, 'id': allowed.pk, 'name': 'Allowed'},
            {'identifier': forbidden.identifier, 'id': forbidden.pk, 'name': 'Forbidden'},
        ],
    )
    assert response.status_code == 403, response.content
    allowed.refresh_from_db()
    forbidden.refresh_from_db()
    assert allowed.name != 'Allowed'
    assert forbidden.name != 'Forbidden'


def test_listing_does_not_query_per_row(api_client, django_assert_max_num_queries):
    plan = make_plan(1)
    user = make_contact(plan, ActionContactPerson.Role.MODERATOR)
    api_client.force_login(user)
    url = action_list_url(plan)
    api_client.get(url)  # warm up caches
    with django_assert_max_num_queries(1000) as one_action:
        api_client.get(url)
    for _ in range(5):
        action = ActionFactory.create(plan=plan)
        ActionContactFactory.create(action=action, person=user.person, role=ActionContactPerson.Role.MODERATOR)
    with django_assert_max_num_queries(len(one_action.captured_queries)):
        response = api_client.get(url)
    assert all(row['modifiable_by_user'] for row in list_rows(response))


def test_publishable_by_matches_can_publish_action():
    for make_situation, _ in SITUATIONS:
        s = make_situation()
        publishable = Action.objects.qs.filter(plan=s.plan).publishable_by(s.user)
        assert (s.action in publishable) is s.user.can_publish_action(s.action), make_situation.__name__


def test_merged_action_is_read_only_for_its_contact_person(api_client):
    plan = make_plan(0)
    user = make_contact(plan, ActionContactPerson.Role.EDITOR)
    action = plan.actions.get()
    action.merged_with = ActionFactory.create(plan=plan)
    action.save()
    api_client.force_login(user)
    rows = {row['id']: row for row in list_rows(api_client.get(action_list_url(plan)))}
    assert rows[action.pk]['read_only_reason'] == ActionReadOnlyReason.NOT_PERMITTED.value
    assert user.get_action_read_only_reason(action) == ActionReadOnlyReason.NOT_PERMITTED
    assert not user.can_edit_some_action_live(plan)


def test_merged_action_stays_editable_for_a_plan_admin(api_client):
    plan = make_plan(0)
    user = make_plan_admin(plan)
    action = plan.actions.get()
    action.merged_with = ActionFactory.create(plan=plan)
    action.save()
    api_client.force_login(user)
    rows = {row['id']: row for row in list_rows(api_client.get(action_list_url(plan)))}
    assert rows[action.pk]['read_only_reason'] is None


def test_moderator_on_a_workflow_without_steps_may_edit(api_client):
    """`User.can_publish_action()` rejects only workflows of more than one step, so the row flags do too."""
    plan = make_plan(0)
    plan.features.moderation_workflow = WorkflowFactory.create()
    plan.features.save()
    user = make_contact(plan, ActionContactPerson.Role.MODERATOR)
    action = plan.actions.get()
    assert user.can_publish_action(action)
    api_client.force_login(user)
    [row] = list_rows(api_client.get(action_list_url(plan)))
    assert row['read_only_reason'] is None
    assert user.can_edit_some_action_live(plan)


def move_request(action: Action, left_sibling: Action | None, **changes) -> list[dict]:
    """Build what the action list sends to move `action` behind `left_sibling`."""
    return [
        {
            'id': action.pk,
            'uuid': str(action.uuid),
            'parent': None,
            'left_sibling': str(left_sibling.uuid) if left_sibling is not None else None,
            'name': action.name,
            'identifier': action.identifier,
            **changes,
        }
    ]


def test_action_with_a_draft_can_still_be_moved(api_client):
    """Publishing a draft keeps the live order, so a draft does not stand in the way of a move."""
    plan = make_plan(0)
    user = make_plan_admin(plan)
    first = plan.actions.get()
    second = ActionFactory.create(plan=plan)
    add_draft(plan)
    second.refresh_from_db()
    api_client.force_login(user)
    response = api_client.put(action_list_url(plan), data=move_request(second, None))
    assert response.status_code == 200, response.content
    assert list(plan.actions.order_by('order').values_list('pk', flat=True)) == [second.pk, first.pk]


def test_moving_an_action_with_a_draft_cannot_change_it(api_client):
    plan = make_plan(0)
    user = make_plan_admin(plan)
    ActionFactory.create(plan=plan)
    add_draft(plan)
    action = plan.actions.order_by('order').last()
    assert action is not None
    api_client.force_login(user)
    response = api_client.put(action_list_url(plan), data=move_request(action, None, name='Renamed'))
    assert response.status_code == 403, response.content
    action.refresh_from_db()
    assert action.name != 'Renamed'


def test_moving_does_not_get_around_moderation(api_client):
    plan = make_plan(1)
    user = make_contact(plan, ActionContactPerson.Role.EDITOR)
    action = plan.actions.get()
    api_client.force_login(user)
    response = api_client.put(action_list_url(plan), data=move_request(action, None))
    assert response.status_code == 403, response.content


def test_moving_an_action_with_a_draft_keeps_the_concurrency_check(api_client):
    plan = make_plan(0)
    user = make_plan_admin(plan)
    ActionFactory.create(plan=plan)
    add_draft(plan)
    action = plan.actions.order_by('order').last()
    assert action is not None
    api_client.force_login(user)
    stale = api_client.put(action_list_url(plan), data=move_request(action, None, version=action.version - 1))
    assert stale.status_code == 409, stale.content
    current = api_client.put(action_list_url(plan), data=move_request(action, None, version=action.version))
    assert current.status_code == 200, current.content


def test_moving_an_action_with_a_draft_needs_its_identifier(api_client):
    """Without the identifier, the update would generate a new one on a plan that hides identifiers."""
    plan = make_plan(0)
    user = make_plan_admin(plan)
    ActionFactory.create(plan=plan)
    add_draft(plan)
    action = plan.actions.order_by('order').last()
    assert action is not None
    [row] = move_request(action, None)
    del row['identifier']
    api_client.force_login(user)
    response = api_client.patch(action_detail_url(action), data=row)
    assert response.status_code == 403, response.content


def test_action_list_move_of_an_action_with_a_draft(api_client):
    """The action list moves an action by sending only its position, as a bulk PATCH."""
    plan = make_plan(0)
    user = make_plan_admin(plan)
    first = plan.actions.get()
    second = ActionFactory.create(plan=plan)
    add_draft(plan)
    second.refresh_from_db()
    [row] = move_request(second, None)
    del row['name']
    api_client.force_login(user)
    response = api_client.patch(action_list_url(plan), data=[row])
    assert response.status_code == 200, response.content
    assert list(plan.actions.order_by('order').values_list('pk', flat=True)) == [second.pk, first.pk]
    second.refresh_from_db()
    assert second.identifier == row['identifier']


def test_moving_an_action_with_a_draft_cannot_change_its_uuid(api_client):
    plan = make_plan(0)
    user = make_plan_admin(plan)
    ActionFactory.create(plan=plan)
    add_draft(plan)
    action = plan.actions.order_by('order').last()
    assert action is not None
    old_uuid = action.uuid
    [row] = move_request(action, None)
    row['uuid'] = '00000000-0000-4000-8000-000000000000'
    api_client.force_login(user)
    response = api_client.patch(action_detail_url(action), data=row)
    assert response.status_code == 403, response.content
    action.refresh_from_db()
    assert action.uuid == old_uuid


def test_moving_by_patch_invalidates_the_plan_cache(api_client, django_capture_on_commit_callbacks, monkeypatch):
    """The action list moves actions by PATCH, which must refresh the cached plan data like any other write."""
    plan = make_plan(0)
    plan.create_default_site()
    plan.save()
    user = make_plan_admin(plan)
    second = ActionFactory.create(plan=plan)
    invalidated: list[int] = []
    monkeypatch.setattr(type(plan), 'invalidate_cache', lambda self: invalidated.append(self.pk))
    [row] = move_request(second, None)
    del row['name']
    api_client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.patch(action_list_url(plan), data=[row])
    assert response.status_code == 200, response.content
    assert plan.pk in invalidated


def test_moving_an_action_with_a_draft_cannot_trim_its_name(api_client):
    plan = make_plan(0)
    user = make_plan_admin(plan)
    ActionFactory.create(plan=plan)
    add_draft(plan)
    action = plan.actions.order_by('order').last()
    assert action is not None
    Action.objects.filter(pk=action.pk).update(name=' Padded ')
    action.refresh_from_db()
    api_client.force_login(user)
    response = api_client.put(action_list_url(plan), data=move_request(action, None))
    assert response.status_code == 403, response.content
    action.refresh_from_db()
    assert action.name == ' Padded '


def test_patch_to_a_missing_plan_is_not_found(api_client):
    plan = make_plan(0)
    plan.create_default_site()
    plan.save()
    user = make_plan_admin(plan)
    api_client.force_login(user)
    response = api_client.patch(reverse('action-list', args=(plan.pk + 1000,)), data=[])
    assert response.status_code == 404, response.content
