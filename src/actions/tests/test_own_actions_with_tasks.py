"""
The admin dashboard's "Actions assigned to me" list and the task contacts in it.

The dashboard asks `myPlans { actions(onlyMine: true) }`. When a plan records task assignees, a contact
person of a task counts as one of the action's people for this list, even without being a contact person
of the action itself; `viewerIsContactPerson` then tells the dashboard which rows are the user's own.
"""

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest

from actions.models.features import PlanFeatures
from actions.tests.factories import ActionFactory, ActionTaskContactFactory, ActionTaskFactory, PlanFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

if TYPE_CHECKING:
    from actions.models import Action, Plan
    from people.models import Person

pytestmark = pytest.mark.django_db

OWN_ACTIONS_QUERY = """
    query {
      myPlans {
        identifier
        actions(onlyMine: true, restrictToPubliclyVisible: false) {
          identifier
          viewerIsContactPerson
          tasks {
            name
            viewerIsContactPerson
          }
        }
      }
    }
"""


def _enable_task_assignees(plan: Plan) -> None:
    plan.features.has_action_task_assignees = True
    plan.features.save()


def _staff_person(plan: Plan) -> Person:
    """
    Create a person who can sign in to the admin but has no role in `plan`.

    Signing in revokes staff status from a user who may administer no plan at all, so the person is made a
    general admin of an unrelated plan. That plan has no actions, so `myPlans` does not list it.
    """
    return PersonFactory.create(
        organization=plan.organization,
        user=UserFactory.create(is_staff=True),
        general_admin_plans=[PlanFactory.create()],
    )


def _make_task_contact(action: Action, person: Person, name: str = 'Task'):
    task = ActionTaskFactory.create(action=action, name=name, due_at=datetime.date(2027, 1, 1))
    ActionTaskContactFactory.create(task=task, person=person)
    return task


def _own_actions(client, graphql_client_query_data, person: Person) -> dict[str, list[dict]]:
    client.force_login(person.user)
    data = graphql_client_query_data(OWN_ACTIONS_QUERY)
    return {plan['identifier']: plan['actions'] for plan in data['myPlans']}


def test_an_action_with_a_task_of_mine_is_listed(client, graphql_client_query_data, plan, action):
    _enable_task_assignees(plan)
    person = _staff_person(plan)
    _make_task_contact(action, person, name='Mine')
    ActionTaskFactory.create(action=action, name='Not mine', due_at=datetime.date(2027, 1, 1))

    own = _own_actions(client, graphql_client_query_data, person)

    assert own == {
        plan.identifier: [
            {
                'identifier': action.identifier,
                'viewerIsContactPerson': False,
                'tasks': [
                    {'name': 'Mine', 'viewerIsContactPerson': True},
                    {'name': 'Not mine', 'viewerIsContactPerson': False},
                ],
            },
        ],
    }


def test_task_contacts_are_ignored_without_the_feature(client, graphql_client_query_data, plan, action):
    person = _staff_person(plan)
    _make_task_contact(action, person)

    assert _own_actions(client, graphql_client_query_data, person) == {}


def test_task_contacts_are_ignored_without_the_feature_next_to_own_actions(client, graphql_client_query_data, plan, action):
    """The plan is listed for the user's own action, but the task's action must still be left out."""
    person = _staff_person(plan)
    own_action = ActionFactory.create(plan=plan)
    person.contact_for_actions.add(own_action)
    _make_task_contact(action, person)

    own = _own_actions(client, graphql_client_query_data, person)

    assert [a['identifier'] for a in own[plan.identifier]] == [own_action.identifier]
    assert own[plan.identifier][0]['viewerIsContactPerson'] is True


def test_an_action_contact_still_sees_their_actions(client, graphql_client_query_data, plan, action):
    _enable_task_assignees(plan)
    person = _staff_person(plan)
    person.contact_for_actions.add(action)
    _make_task_contact(action, person)
    other_action = ActionFactory.create(plan=plan)
    _make_task_contact(other_action, person)

    own = _own_actions(client, graphql_client_query_data, person)

    flags = {a['identifier']: a['viewerIsContactPerson'] for a in own[plan.identifier]}
    assert flags == {action.identifier: True, other_action.identifier: False}


def test_a_task_contact_of_another_plan_does_not_leak_into_this_one(client, graphql_client_query_data, plan, action):
    _enable_task_assignees(plan)
    person = _staff_person(plan)
    _make_task_contact(action, person)
    other_plan = PlanFactory.create()
    _enable_task_assignees(other_plan)
    ActionFactory.create(plan=other_plan)

    assert set(_own_actions(client, graphql_client_query_data, person)) == {plan.identifier}


def test_a_non_staff_task_contact_gets_nothing(client, graphql_client_query_data, plan, action):
    """Being a task contact gives no access to the admin, so it must not make the dashboard list anything."""
    _enable_task_assignees(plan)
    person = PersonFactory.create(organization=plan.organization, user=UserFactory.create(is_staff=False))
    _make_task_contact(action, person)

    assert _own_actions(client, graphql_client_query_data, person) == {}


def test_the_flag_ignores_the_contact_person_privacy_setting(client, graphql_client_query_data, plan, action):
    """`contactPersons` is empty when the plan publishes no contact persons; the user's own flag must not be."""
    _enable_task_assignees(plan)
    plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.NONE
    plan.features.save()
    person = _staff_person(plan)
    person.contact_for_actions.add(action)
    _make_task_contact(action, person)

    own = _own_actions(client, graphql_client_query_data, person)

    assert own[plan.identifier][0]['viewerIsContactPerson'] is True
    assert own[plan.identifier][0]['tasks'][0]['viewerIsContactPerson'] is True


def test_the_task_flag_is_false_without_the_feature(client, graphql_client_query_data, plan, action):
    person = _staff_person(plan)
    person.contact_for_actions.add(action)
    _make_task_contact(action, person)

    own = _own_actions(client, graphql_client_query_data, person)

    assert own[plan.identifier][0]['tasks'][0]['viewerIsContactPerson'] is False


def test_the_flags_are_false_for_an_anonymous_user(graphql_client_query_data, plan, action):
    _enable_task_assignees(plan)
    _make_task_contact(action, _staff_person(plan))

    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planActions(plan: $plan) { viewerIsContactPerson tasks { viewerIsContactPerson } }
        }
        """,
        variables={'plan': plan.identifier},
    )

    assert data['planActions'] == [{'viewerIsContactPerson': False, 'tasks': [{'viewerIsContactPerson': False}]}]


def _query_count(client, graphql_client_query_data, person: Person) -> int:
    client.force_login(person.user)
    with CaptureQueriesContext(connection) as ctx:
        graphql_client_query_data(OWN_ACTIONS_QUERY)
    return len(ctx)


def test_the_task_flag_does_not_cost_a_query_per_task(client, graphql_client_query_data):
    def person_with_tasks(task_count: int) -> Person:
        plan = PlanFactory.create()
        _enable_task_assignees(plan)
        person = _staff_person(plan)
        action = ActionFactory.create(plan=plan)
        for i in range(task_count):
            _make_task_contact(action, person, name=f'Task {i}')
        return person

    small_count = _query_count(client, graphql_client_query_data, person_with_tasks(2))
    large_count = _query_count(client, graphql_client_query_data, person_with_tasks(8))

    assert large_count == small_count, f'{large_count} queries for 8 tasks vs {small_count} for 2'


def test_the_flags_follow_a_draft(client, graphql_client_query_data, plan, action, plan_admin_person):
    """
    At a draft workflow state, the flags must answer for the draft's contact persons, not the published ones.

    The draft drops the user as a contact person of the action and makes them one of the task, which the
    published rows say the opposite of. The revision content is edited directly, as in the task assignment
    tests, so that it genuinely differs from the database.
    """
    from wagtail.models import Revision

    _enable_task_assignees(plan)
    plan_admin_person.contact_for_actions.add(action)
    other_person = _staff_person(plan)
    _make_task_contact(action, other_person)
    action.refresh_from_db()

    content = action.serializable_data()
    content.setdefault('attributes', {})
    content['contact_persons'] = []
    (task_contact,) = content['tasks'][0]['contact_persons']
    task_contact['person'] = plan_admin_person.pk
    base_revision = action.save_revision(user=plan_admin_person.user)
    revision: Revision = Revision(
        content_type=base_revision.content_type,
        base_content_type=base_revision.base_content_type,
        object_id=str(action.pk),
    )
    revision.content = content
    revision.save()
    action.latest_revision = revision
    action.has_unpublished_changes = True
    action.save(update_fields=['latest_revision', 'has_unpublished_changes'])
    client.force_login(plan_admin_person.user)

    query = """
        query($plan: ID!) @workflow(state: %s) {
          planActions(plan: $plan) { viewerIsContactPerson tasks { viewerIsContactPerson } }
        }
    """
    published = graphql_client_query_data(query % 'PUBLISHED', variables={'plan': plan.identifier})
    draft = graphql_client_query_data(query % 'DRAFT', variables={'plan': plan.identifier})

    assert published['planActions'] == [{'viewerIsContactPerson': True, 'tasks': [{'viewerIsContactPerson': False}]}]
    assert draft['planActions'] == [{'viewerIsContactPerson': False, 'tasks': [{'viewerIsContactPerson': True}]}]
