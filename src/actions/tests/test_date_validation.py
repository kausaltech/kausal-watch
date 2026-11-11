"""
Validation of an action's start and end date and of a task's completion date.

The checks only apply when a save changes one of the dates involved, so that existing rows that break
them can still be edited otherwise. See `actions.validation`.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin

from actions.models import ActionTask
from actions.tests.factories import ActionFactory, ActionTaskFactory, PlanFactory
from actions.validation import (
    ACTION_END_BEFORE_START_MESSAGE,
    TASK_COMPLETED_IN_FUTURE_MESSAGE,
    get_action_dates_error,
    get_task_completion_date_error,
)
from admin_site.tests.factories import BuiltInFieldCustomizationFactory, ClientPlanFactory
from admin_site.tests.utils import post_data

if TYPE_CHECKING:
    from django.test import Client

    from actions.models import Action, Plan
    from users.models import User

pytestmark = pytest.mark.django_db

EditableBy = InstancesEditableByMixin.EditableBy
VisibleFor = InstancesVisibleForMixin.VisibleFor

# Shortly before midnight UTC: it's already the next day in Helsinki, but still the same day in New York.
NOW = datetime.datetime(2026, 1, 14, 23, 30, tzinfo=datetime.UTC)
UTC_TODAY = datetime.date(2026, 1, 14)
HELSINKI_TODAY = datetime.date(2026, 1, 15)
FAR_FUTURE = datetime.date(2100, 1, 1)


@pytest.fixture
def frozen_now():
    with patch('django.utils.timezone.now', return_value=NOW):
        yield


def _edit_url(action: Action) -> str:
    return action.get_admin_edit_url()


def _unchanged_post_data(client: Client, user: User, action: Action) -> dict:
    """Return what submitting the user's edit form of the action unchanged would post."""
    ClientPlanFactory.create(plan=action.plan)
    client.force_login(user)
    response = client.get(_edit_url(action))
    assert response.status_code == 200
    data = post_data(response.context['form'])
    return data


def _customize(plan: Plan, field_name: str, visible_for: VisibleFor, editable_by: EditableBy) -> None:
    BuiltInFieldCustomizationFactory.create(
        plan=plan, field_name=field_name, instances_visible_for=visible_for, instances_editable_by=editable_by
    )


@pytest.mark.parametrize(
    ('start_date', 'end_date', 'is_valid'),
    [
        (datetime.date(2026, 1, 1), datetime.date(2026, 12, 31), True),
        (datetime.date(2026, 1, 1), datetime.date(2026, 1, 1), True),
        (datetime.date(2026, 1, 2), datetime.date(2026, 1, 1), False),
        (None, datetime.date(2026, 1, 1), True),
        (datetime.date(2026, 1, 1), None, True),
    ],
)
def test_action_dates_rule(start_date, end_date, is_valid):
    assert (get_action_dates_error(start_date, end_date) is None) == is_valid


@pytest.mark.parametrize(
    ('timezone', 'completed_at', 'is_valid'),
    [
        # It's already the 15th in Helsinki, so that's not in the future, even though it is in UTC.
        ('Europe/Helsinki', HELSINKI_TODAY, True),
        ('Europe/Helsinki', HELSINKI_TODAY + datetime.timedelta(days=1), False),
        # It's still the 14th in New York, so the 15th is in the future, even though it isn't in UTC.
        ('America/New_York', UTC_TODAY, True),
        ('America/New_York', UTC_TODAY + datetime.timedelta(days=1), False),
        ('UTC', None, True),
    ],
)
def test_task_completion_date_rule_uses_plans_timezone(frozen_now, timezone, completed_at, is_valid):
    plan = PlanFactory.create(timezone=timezone)
    assert (get_task_completion_date_error(completed_at, plan) is None) == is_valid


class TestActionAdmin:
    def test_rejects_end_date_before_start_date(self, client, action, plan_admin_user):
        data = _unchanged_post_data(client, plan_admin_user, action)
        data['start_date'] = '2026-06-01'
        data['end_date'] = '2026-05-01'

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 200
        assert response.context['form'].errors['end_date'] == [ACTION_END_BEFORE_START_MESSAGE]
        action.refresh_from_db()
        assert action.start_date is None
        assert action.end_date is None

    def test_accepts_consistent_dates(self, client, action, plan_admin_user):
        data = _unchanged_post_data(client, plan_admin_user, action)
        data['start_date'] = '2026-05-01'
        data['end_date'] = '2026-06-01'

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 302, response.context['form'].errors
        action.refresh_from_db()
        assert action.end_date == datetime.date(2026, 6, 1)

    def test_accepts_unrelated_change_to_action_with_invalid_dates(self, client, action, plan_admin_user):
        action.start_date = datetime.date(2026, 6, 1)
        action.end_date = datetime.date(2026, 5, 1)
        action.save()
        data = _unchanged_post_data(client, plan_admin_user, action)
        data['name'] = 'Renamed'

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 302, response.context['form'].errors
        action.refresh_from_db()
        assert action.name == 'Renamed'

    @pytest.mark.parametrize(
        ('visible_for', 'editable_by'),
        [
            pytest.param(VisibleFor.PLAN_ADMINS, EditableBy.PLAN_ADMINS, id='hidden'),
            pytest.param(VisibleFor.PUBLIC, EditableBy.PLAN_ADMINS, id='read-only'),
        ],
    )
    def test_puts_error_on_start_date_if_user_cannot_edit_end_date(
        self, client, action, action_contact_person_user, visible_for, editable_by
    ):
        action.end_date = datetime.date(2026, 5, 1)
        action.save()
        _customize(action.plan, 'end_date', visible_for, editable_by)
        data = _unchanged_post_data(client, action_contact_person_user, action)
        data['start_date'] = '2026-06-01'

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 200
        assert response.context['form'].errors['start_date'] == [ACTION_END_BEFORE_START_MESSAGE]
        action.refresh_from_db()
        assert action.start_date is None

    def test_accepts_unrelated_change_if_user_cannot_see_invalid_end_date(self, client, action, action_contact_person_user):
        action.start_date = datetime.date(2026, 6, 1)
        action.end_date = datetime.date(2026, 5, 1)
        action.save()
        _customize(action.plan, 'end_date', VisibleFor.PLAN_ADMINS, EditableBy.PLAN_ADMINS)
        data = _unchanged_post_data(client, action_contact_person_user, action)
        data['name'] = 'Renamed'

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 302, response.context['form'].errors
        action.refresh_from_db()
        assert action.name == 'Renamed'


class TestTaskAdmin:
    @staticmethod
    def _add_task(data: dict, completed_at: datetime.date) -> None:
        index = int(data['tasks-TOTAL_FORMS'])
        data['tasks-TOTAL_FORMS'] = str(index + 1)
        prefix = f'tasks-{index}'
        data |= {
            f'{prefix}-name': 'New task',
            f'{prefix}-due_at': '2025-12-31',
            f'{prefix}-state': ActionTask.COMPLETED,
            f'{prefix}-completed_at': completed_at.isoformat(),
            f'{prefix}-responsible_parties-TOTAL_FORMS': '0',
            f'{prefix}-responsible_parties-INITIAL_FORMS': '0',
            f'{prefix}-contact_persons-TOTAL_FORMS': '0',
            f'{prefix}-contact_persons-INITIAL_FORMS': '0',
        }

    @staticmethod
    def _task_form_errors(response) -> list[dict]:
        return response.context['form'].formsets['tasks'].errors

    def test_rejects_new_task_completed_in_the_future(self, client, action, plan_admin_user, frozen_now):
        action.plan.timezone = 'Europe/Helsinki'
        action.plan.save()
        data = _unchanged_post_data(client, plan_admin_user, action)
        self._add_task(data, HELSINKI_TODAY + datetime.timedelta(days=1))

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 200
        assert self._task_form_errors(response)[0]['completed_at'] == [TASK_COMPLETED_IN_FUTURE_MESSAGE]
        assert not action.tasks.exists()

    def test_accepts_new_task_completed_today_in_plans_timezone(self, client, action, plan_admin_user, frozen_now):
        action.plan.timezone = 'Europe/Helsinki'
        action.plan.save()
        data = _unchanged_post_data(client, plan_admin_user, action)
        # Tomorrow in UTC
        self._add_task(data, HELSINKI_TODAY)

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 302, self._task_form_errors(response)
        assert action.tasks.get().completed_at == HELSINKI_TODAY

    def test_rejects_existing_task_moved_into_the_future(self, client, action, plan_admin_user):
        task = ActionTaskFactory.create(action=action, state=ActionTask.COMPLETED, completed_at=datetime.date(2020, 1, 1))
        data = _unchanged_post_data(client, plan_admin_user, action)
        data['tasks-0-completed_at'] = FAR_FUTURE.isoformat()

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 200
        assert self._task_form_errors(response)[0]['completed_at'] == [TASK_COMPLETED_IN_FUTURE_MESSAGE]
        task.refresh_from_db()
        assert task.completed_at == datetime.date(2020, 1, 1)

    def test_accepts_unrelated_change_to_task_completed_in_the_future(self, client, action, plan_admin_user):
        task = ActionTaskFactory.create(action=action, state=ActionTask.COMPLETED, completed_at=FAR_FUTURE)
        data = _unchanged_post_data(client, plan_admin_user, action)
        data['tasks-0-name'] = 'Renamed task'

        response = client.post(_edit_url(action), data=data)

        assert response.status_code == 302, self._task_form_errors(response)
        task.refresh_from_db()
        assert task.name == 'Renamed task'


class TestActionApi:
    def test_patch_rejects_end_date_before_stored_start_date(self, api_client, action, action_detail_url, plan_admin_user):
        action.start_date = datetime.date(2026, 6, 1)
        action.save()
        api_client.force_login(plan_admin_user)

        response = api_client.patch(action_detail_url, data={'end_date': '2026-05-01'})

        assert response.status_code == 400
        assert response.json_data['end_date'] == [ACTION_END_BEFORE_START_MESSAGE]
        action.refresh_from_db()
        assert action.end_date is None

    def test_patch_puts_error_on_start_date_if_only_that_is_sent(self, api_client, action, action_detail_url, plan_admin_user):
        action.end_date = datetime.date(2026, 5, 1)
        action.save()
        api_client.force_login(plan_admin_user)

        response = api_client.patch(action_detail_url, data={'start_date': '2026-06-01'})

        assert response.status_code == 400
        assert response.json_data['start_date'] == [ACTION_END_BEFORE_START_MESSAGE]

    def test_put_rejects_end_date_before_start_date(self, api_client, plan, action, action_detail_url, plan_admin_user):
        api_client.force_login(plan_admin_user)

        response = api_client.put(
            action_detail_url,
            data={
                'id': action.pk,
                'identifier': action.identifier,
                'name': action.name,
                'plan': plan.pk,
                'start_date': '2026-06-01',
                'end_date': '2026-05-01',
            },
        )

        assert response.status_code == 400
        assert response.json_data['end_date'] == [ACTION_END_BEFORE_START_MESSAGE]

    def test_bulk_put_checks_each_row_against_its_own_action(self, api_client, plan, action_list_url, plan_admin_user):
        valid = ActionFactory.create(plan=plan, start_date=datetime.date(2026, 1, 1))
        invalid = ActionFactory.create(plan=plan, start_date=datetime.date(2026, 6, 1))
        api_client.force_login(plan_admin_user)

        response = api_client.put(
            action_list_url,
            data=[
                {'id': action.pk, 'identifier': action.identifier, 'name': action.name, 'end_date': '2026-05-01'}
                for action in (valid, invalid)
            ],
        )

        assert response.status_code == 400
        # Errors are keyed by the index of the row
        assert response.json_data == {'1': {'end_date': [ACTION_END_BEFORE_START_MESSAGE]}}

    def test_bulk_put_accepts_unrelated_change_to_action_with_invalid_dates(
        self, api_client, plan, action_list_url, plan_admin_user
    ):
        action = ActionFactory.create(plan=plan, start_date=datetime.date(2026, 6, 1), end_date=datetime.date(2026, 5, 1))
        api_client.force_login(plan_admin_user)

        response = api_client.put(
            action_list_url,
            data=[
                {
                    'id': action.pk,
                    'identifier': action.identifier,
                    'name': 'Renamed',
                    # A client that writes back what it read sends the stored dates unchanged.
                    'start_date': '2026-06-01',
                    'end_date': '2026-05-01',
                }
            ],
        )

        assert response.status_code == 200, response.content
        action.refresh_from_db()
        assert action.name == 'Renamed'


class TestTaskApi:
    @staticmethod
    def _payload(task: ActionTask, **fields) -> dict:
        return {
            'id': task.pk,
            'action': task.action_id,
            'name': task.name,
            'due_at': str(task.due_at),
            'state': task.state,
            **fields,
        }

    def test_post_rejects_completion_date_in_the_future(self, api_client, action, action_task_list_url, plan_admin_user):
        api_client.force_login(plan_admin_user)

        response = api_client.post(
            action_task_list_url,
            data={
                'action': action.pk,
                'name': 'A task',
                'state': ActionTask.COMPLETED,
                'due_at': '2025-12-31',
                'completed_at': FAR_FUTURE.isoformat(),
            },
        )

        assert response.status_code == 400
        assert response.json_data['completed_at'] == [TASK_COMPLETED_IN_FUTURE_MESSAGE]
        assert not action.tasks.exists()

    def test_post_accepts_completion_date_today_in_plans_timezone(
        self, api_client, plan, action, action_task_list_url, plan_admin_user, frozen_now
    ):
        plan.timezone = 'Europe/Helsinki'
        plan.save()
        api_client.force_login(plan_admin_user)

        response = api_client.post(
            action_task_list_url,
            data={
                'action': action.pk,
                'name': 'A task',
                'state': ActionTask.COMPLETED,
                'due_at': '2025-12-31',
                'completed_at': HELSINKI_TODAY.isoformat(),
            },
        )

        assert response.status_code == 201, response.content

    def test_bulk_put_rejects_completion_date_moved_into_the_future(
        self, api_client, action, action_task_list_url, plan_admin_user
    ):
        task = ActionTaskFactory.create(action=action, state=ActionTask.COMPLETED, completed_at=datetime.date(2020, 1, 1))
        api_client.force_login(plan_admin_user)

        response = api_client.put(action_task_list_url, data=[self._payload(task, completed_at=FAR_FUTURE.isoformat())])

        assert response.status_code == 400
        assert response.json_data['0']['completed_at'] == [TASK_COMPLETED_IN_FUTURE_MESSAGE]
        task.refresh_from_db()
        assert task.completed_at == datetime.date(2020, 1, 1)

    def test_bulk_put_accepts_unchanged_completion_date_in_the_future(
        self, api_client, action, action_task_list_url, plan_admin_user
    ):
        task = ActionTaskFactory.create(action=action, state=ActionTask.COMPLETED, completed_at=FAR_FUTURE)
        api_client.force_login(plan_admin_user)

        response = api_client.put(
            action_task_list_url,
            data=[self._payload(task, name='Renamed task', completed_at=FAR_FUTURE.isoformat())],
        )

        assert response.status_code == 200, response.content
        task.refresh_from_db()
        assert task.name == 'Renamed task'
