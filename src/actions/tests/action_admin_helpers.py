"""Helpers for the tests that go through the action admin views."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from django.contrib.messages import get_messages
from django.urls import reverse

from bs4 import BeautifulSoup

from actions.models import ActionContactPerson
from actions.models.action import ActionModeratorApprovalTask
from actions.tests.factories import ActionContactFactory, WorkflowFactory, WorkflowTaskFactory
from admin_site.tests.factories import ClientPlanFactory
from admin_site.tests.utils import post_data
from orgs.tests.factories import OrganizationFactory, OrganizationPlanAdminFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

if TYPE_CHECKING:
    from django.test import Client
    from django.test.client import _MonkeyPatchedWSGIResponse as HttpResponse

    from actions.models import Action, Plan
    from users.models import User


def _url(view_name: str, *args: Any) -> str:
    return reverse(f'wagtailsnippets_actions_action:{view_name}', args=args)


def index_url() -> str:
    return _url('list')


def create_url() -> str:
    return _url('add')


def edit_url(action: Action) -> str:
    return _url('edit', action.pk)


def delete_url(action: Action) -> str:
    return _url('delete', action.pk)


def unpublish_url(action: Action) -> str:
    return _url('unpublish', action.pk)


def usage_url(action: Action) -> str:
    return _url('usage', action.pk)


def history_url(action: Action) -> str:
    return _url('history', action.pk)


def workflow_history_url(action: Action) -> str:
    return _url('workflow_history', action.pk)


def workflow_history_detail_url(action: Action, workflow_state_id: int) -> str:
    return _url('workflow_history_detail', action.pk, workflow_state_id)


def compare_url(action: Action, revision_a: int, revision_b: int) -> str:
    return _url('revisions_compare', action.pk, revision_a, revision_b)


def confirm_workflow_cancellation_url(action: Action) -> str:
    return _url('confirm_workflow_cancellation', action.pk)


def collect_workflow_action_data_url(action: Action, action_name: str, task_state_id: int) -> str:
    return _url('collect_workflow_action_data', action.pk, action_name, task_state_id)


def mark_as_complete_url(action: Action, report_pk: int) -> str:
    return _url('mark_action_as_complete', action.pk, report_pk)


def undo_marking_as_complete_url(action: Action, report_pk: int) -> str:
    return _url('undo_marking_action_as_complete', action.pk, report_pk)


def enable_moderation(plan: Plan, task_count: int = 1) -> None:
    workflow = WorkflowFactory.create()
    for i in range(task_count):
        task = ActionModeratorApprovalTask.objects.create(name=f'Moderation step {i}', active=True)
        WorkflowTaskFactory.create(workflow=workflow, task=task, sort_order=i)
    plan.features.moderation_workflow = workflow
    plan.features.save()


def make_superuser(plan: Plan) -> User:
    ClientPlanFactory.create(plan=plan)
    return UserFactory.create(is_superuser=True, selected_admin_plan=plan)


def make_plan_admin(plan: Plan) -> User:
    ClientPlanFactory.create(plan=plan)
    user = UserFactory.create()
    PersonFactory.create(user=user, general_admin_plans=[plan])
    return user


def plan_admin_for(action: Action) -> User:
    return make_plan_admin(action.plan)


def superuser_for(action: Action) -> User:
    return make_superuser(action.plan)


def make_contact_person(action: Action, role: ActionContactPerson.Role = ActionContactPerson.Role.EDITOR) -> User:
    ClientPlanFactory.create(plan=action.plan)
    user = UserFactory.create()
    person = PersonFactory.create(user=user)
    ActionContactFactory.create(action=action, person=person, role=role)
    return user


def make_moderator(action: Action) -> User:
    return make_contact_person(action, ActionContactPerson.Role.MODERATOR)


def make_organization_admin(action: Action) -> User:
    """Create an organization admin whose organization is the action's primary organization."""
    ClientPlanFactory.create(plan=action.plan)
    organization = OrganizationFactory.create()
    action.primary_org = organization
    action.save(update_fields=['primary_org'])
    user = UserFactory.create()
    person = PersonFactory.create(user=user, organization=organization)
    OrganizationPlanAdminFactory.create(organization=organization, plan=action.plan, person=person)
    return user


def get_edit_page(client: Client, user: User, action: Action) -> HttpResponse:
    client.force_login(user)
    return client.get(edit_url(action))


def unchanged_post_data(client: Client, user: User, action: Action) -> dict[str, Any]:
    """Return what submitting the user's edit form of the action unchanged would post."""
    client.force_login(user)
    response = client.get(edit_url(action))
    assert response.status_code == 200
    return post_data(response.context['form'])


def post_edit(client: Client, user: User, action: Action, button: str | None = None, **changes: Any) -> HttpResponse:
    """Submit the user's edit form of the action with the given changes, pressing the given action menu button."""
    data = unchanged_post_data(client, user, action)
    data.update(changes)
    if button is not None:
        data[f'action-{button}'] = 'true'
    return client.post(edit_url(action), data=data)


def post_workflow_action(
    client: Client, user: User, action: Action, name: str, extra_data: dict[str, Any] | None = None, **changes: Any
) -> HttpResponse:
    if extra_data is not None:
        changes['workflow-action-extra-data'] = json.dumps(extra_data)
    return post_edit(client, user, action, 'workflow-action', **{'workflow-action-name': name}, **changes)


def message_texts(response: HttpResponse) -> list[str]:
    return [str(message.message) for message in get_messages(response.wsgi_request)]


def action_menu_names(response: HttpResponse) -> list[str]:
    """Return the names of the buttons the edit page's action menu offers."""
    menu = response.context.get('action_menu')
    if menu is None:
        return []
    return [item.name for item in (menu.default_item, *menu.menu_items) if item is not None]


def status_side_panel_text(response: HttpResponse) -> str:
    """Return the visible text of the edit page's status side panel."""
    soup = BeautifulSoup(response.content.decode(), 'html.parser')
    panel = soup.select_one('[data-side-panel="status"]')
    assert panel is not None
    return ' '.join(panel.get_text(' ').split())


def table_rows(response: HttpResponse) -> list[str]:
    soup = BeautifulSoup(response.content.decode(), 'html.parser')
    return [' '.join(row.get_text(' ').split()) for row in soup.select('table tr')]
