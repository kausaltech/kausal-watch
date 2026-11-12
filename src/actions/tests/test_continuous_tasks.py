"""
Continuous action tasks, which may go without a due date.

A task that isn't continuous must still have one. The admin form, the REST serializer and a database
constraint enforce this.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType
from django.db import IntegrityError, transaction
from django.urls import reverse

import pytest

from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin

from actions.action_admin import ActionAdmin
from actions.models import ActionTask
from actions.monitoring_quality import determine_future_task
from actions.tests.factories import ActionStatusFactory, ActionTaskFactory
from actions.validation import TASK_DUE_DATE_REQUIRED_MESSAGE
from admin_site.tests.factories import BuiltInFieldCustomizationFactory, ClientPlanFactory
from admin_site.tests.utils import post_data

if TYPE_CHECKING:
    from django.test import Client

    from actions.models import Action, Plan
    from users.models import User

pytestmark = pytest.mark.django_db

EditableBy = InstancesEditableByMixin.EditableBy
VisibleFor = InstancesVisibleForMixin.VisibleFor


def _edit_url(action: Action) -> str:
    return reverse(ActionAdmin().url_helper.get_action_url_name('edit'), kwargs={'instance_pk': action.pk})


def _unchanged_post_data(client: Client, user: User, action: Action) -> dict:
    """Return what submitting the user's edit form of the action unchanged would post."""
    ClientPlanFactory.create(plan=action.plan)
    client.force_login(user)
    response = client.get(_edit_url(action))
    assert response.status_code == 200
    return post_data(response.context['form'])


def _customize_task_field(plan: Plan, field_name: str, visible_for: VisibleFor, editable_by: EditableBy) -> None:
    BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get_for_model(ActionTask),
        field_name=field_name,
        instances_visible_for=visible_for,
        instances_editable_by=editable_by,
    )


def test_database_rejects_non_continuous_task_without_due_date(action):
    with pytest.raises(IntegrityError), transaction.atomic():
        ActionTaskFactory.create(action=action, due_at=None)


def test_database_accepts_continuous_task_without_due_date(action):
    task = ActionTaskFactory.create(action=action, is_continuous=True, due_at=None)
    task.refresh_from_db()
    assert task.due_at is None


def test_continuous_task_without_due_date_is_not_late(action):
    for identifier in ('not_started', 'on_time', 'late'):
        ActionStatusFactory.create(plan=action.plan, identifier=identifier)
    ActionTaskFactory.create(action=action, is_continuous=True, due_at=None)
    action.recalculate_status()
    action.refresh_from_db()
    assert action.status is not None
    assert action.status.identifier != 'late'


def test_continuous_task_without_due_date_counts_as_future_task(action):
    assert not determine_future_task(action)
    ActionTaskFactory.create(action=action, is_continuous=True, due_at=None, state=ActionTask.IN_PROGRESS)
    assert determine_future_task(action)


class TestTaskAdmin:
    @staticmethod
    def _add_task(data: dict, *, is_continuous: bool | None, due_at: str) -> None:
        index = int(data['tasks-TOTAL_FORMS'])
        data['tasks-TOTAL_FORMS'] = str(index + 1)
        prefix = f'tasks-{index}'
        data |= {
            f'{prefix}-name': 'New task',
            f'{prefix}-due_at': due_at,
            f'{prefix}-state': ActionTask.IN_PROGRESS,
            f'{prefix}-completed_at': '',
            f'{prefix}-responsible_parties-TOTAL_FORMS': '0',
            f'{prefix}-responsible_parties-INITIAL_FORMS': '0',
            f'{prefix}-contact_persons-TOTAL_FORMS': '0',
            f'{prefix}-contact_persons-INITIAL_FORMS': '0',
        }
        if is_continuous:
            data[f'{prefix}-is_continuous'] = 'on'

    @staticmethod
    def _task_form_errors(response) -> list[dict]:
        return response.context['form'].formsets['tasks'].errors

    def test_accepts_continuous_task_without_due_date(self, client, action, plan_admin_user):
        data = _unchanged_post_data(client, plan_admin_user, action)
        self._add_task(data, is_continuous=True, due_at='')

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 302, self._task_form_errors(response)
        task = action.tasks.get()
        assert task.is_continuous
        assert task.due_at is None

    def test_rejects_non_continuous_task_without_due_date(self, client, action, plan_admin_user):
        data = _unchanged_post_data(client, plan_admin_user, action)
        self._add_task(data, is_continuous=False, due_at='')

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 200
        errors = self._task_form_errors(response)[0]
        assert errors == {'due_at': [TASK_DUE_DATE_REQUIRED_MESSAGE]}
        assert not action.tasks.exists()

    def test_rejects_unsetting_continuity_of_task_without_due_date(self, client, action, plan_admin_user):
        task = ActionTaskFactory.create(action=action, is_continuous=True, due_at=None)
        data = _unchanged_post_data(client, plan_admin_user, action)
        data.pop('tasks-0-is_continuous')

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 200
        assert self._task_form_errors(response)[0] == {'due_at': [TASK_DUE_DATE_REQUIRED_MESSAGE]}
        task.refresh_from_db()
        assert task.is_continuous

    @pytest.mark.parametrize(
        ('visible_for', 'editable_by'),
        [
            pytest.param(VisibleFor.PLAN_ADMINS, EditableBy.PLAN_ADMINS, id='hidden'),
            pytest.param(VisibleFor.PUBLIC, EditableBy.PLAN_ADMINS, id='read-only'),
        ],
    )
    def test_puts_error_on_continuity_if_user_cannot_edit_due_date(
        self, client, action, action_contact_person_user, visible_for, editable_by
    ):
        _customize_task_field(action.plan, 'due_at', visible_for, editable_by)
        data = _unchanged_post_data(client, action_contact_person_user, action)
        self._add_task(data, is_continuous=False, due_at='')

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 200
        assert self._task_form_errors(response)[0] == {'is_continuous': [TASK_DUE_DATE_REQUIRED_MESSAGE]}
        assert not action.tasks.exists()

    @pytest.mark.parametrize(
        ('visible_for', 'editable_by'),
        [
            pytest.param(VisibleFor.PLAN_ADMINS, EditableBy.PLAN_ADMINS, id='hidden'),
            pytest.param(VisibleFor.PUBLIC, EditableBy.PLAN_ADMINS, id='read-only'),
        ],
    )
    def test_requires_due_date_if_user_cannot_edit_continuity(
        self, client, action, action_contact_person_user, visible_for, editable_by
    ):
        # Django skips the database constraint for a form that leaves out one of its fields, so without the
        # form's own check, this would fail on saving.
        _customize_task_field(action.plan, 'is_continuous', visible_for, editable_by)
        data = _unchanged_post_data(client, action_contact_person_user, action)
        self._add_task(data, is_continuous=None, due_at='')

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 200
        assert self._task_form_errors(response)[0] == {'due_at': [TASK_DUE_DATE_REQUIRED_MESSAGE]}
        assert not action.tasks.exists()

    def test_accepts_unrelated_change_if_user_cannot_see_either_field(self, client, action, action_contact_person_user):
        task = ActionTaskFactory.create(action=action, is_continuous=True, due_at=None)
        for field_name in ('due_at', 'is_continuous'):
            _customize_task_field(action.plan, field_name, VisibleFor.PLAN_ADMINS, EditableBy.PLAN_ADMINS)
        data = _unchanged_post_data(client, action_contact_person_user, action)
        data['tasks-0-name'] = 'Renamed task'

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 302, self._task_form_errors(response)
        task.refresh_from_db()
        assert task.name == 'Renamed task'
        assert task.due_at is None


class TestTaskApi:
    def test_post_accepts_continuous_task_without_due_date(self, api_client, action, action_task_list_url, plan_admin_user):
        api_client.force_login(plan_admin_user)

        response = api_client.post(
            action_task_list_url,
            data={'action': action.pk, 'name': 'A task', 'state': ActionTask.IN_PROGRESS, 'is_continuous': True},
        )

        assert response.status_code == 201, response.content
        assert response.json_data['is_continuous'] is True
        assert response.json_data['due_at'] is None

    def test_post_rejects_non_continuous_task_without_due_date(self, api_client, action, action_task_list_url, plan_admin_user):
        api_client.force_login(plan_admin_user)

        response = api_client.post(
            action_task_list_url,
            data={'action': action.pk, 'name': 'A task', 'state': ActionTask.IN_PROGRESS},
        )

        assert response.status_code == 400
        assert response.json_data['due_at'] == [TASK_DUE_DATE_REQUIRED_MESSAGE]
        assert not action.tasks.exists()

    def test_bulk_put_checks_each_row_against_its_own_task(self, api_client, action, action_task_list_url, plan_admin_user):
        continuous = ActionTaskFactory.create(action=action, is_continuous=True, due_at=None)
        other = ActionTaskFactory.create(action=action, due_at=datetime.date(2030, 1, 1))
        api_client.force_login(plan_admin_user)

        response = api_client.put(
            action_task_list_url,
            data=[
                {'id': task.pk, 'action': action.pk, 'name': task.name, 'state': task.state, 'due_at': None}
                for task in (continuous, other)
            ],
        )

        assert response.status_code == 400
        # Errors are keyed by the index of the row
        assert response.json_data == {'1': {'due_at': [TASK_DUE_DATE_REQUIRED_MESSAGE]}}
        other.refresh_from_db()
        assert other.due_at == datetime.date(2030, 1, 1)
