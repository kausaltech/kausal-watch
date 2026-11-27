"""Who may edit an action's contact persons, depending on whether the plan distinguishes contact person roles."""

from __future__ import annotations

import re
from types import SimpleNamespace

from django.core.exceptions import ValidationError
from django.urls import reverse

import pytest

from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin

from actions.mail import ActionModeratorApprovalTaskStateSubmissionEmailNotifier
from actions.models import Action, ActionContactPerson, Plan
from actions.models.action import ActionModeratorApprovalTask
from actions.tests.action_admin_helpers import edit_url
from actions.tests.factories import (
    ActionContactFactory,
    ActionFactory,
    PlanFactory,
    WorkflowFactory,
    WorkflowTaskFactory,
)
from admin_site.tests.factories import BuiltInFieldCustomizationFactory, ClientPlanFactory
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db

Role = ActionContactPerson.Role


def _plan(*, has_roles: bool) -> Plan:
    plan = PlanFactory.create()
    plan.features.has_action_contact_person_roles = has_roles
    plan.features.save()
    ClientPlanFactory.create(plan=plan)
    return plan


def _contact_person(action: Action, role: Role) -> ActionContactPerson:
    return ActionContactFactory.create(action=action, role=role)


@pytest.mark.parametrize(
    ('has_roles', 'role', 'expected'),
    [
        (True, Role.MODERATOR, [Role.EDITOR]),
        (True, Role.EDITOR, []),
        (False, Role.MODERATOR, []),
        (False, Role.EDITOR, []),
    ],
)
def test_editable_contact_person_roles_of_a_contact_person(has_roles, role, expected):
    action = ActionFactory.create(plan=_plan(has_roles=has_roles))
    user = _contact_person(action, role).person.user
    assert user is not None
    assert list(user.get_editable_contact_person_roles(action)) == expected


@pytest.mark.parametrize('has_roles', [True, False])
def test_plan_admin_may_edit_contact_persons_of_all_roles(has_roles):
    plan = _plan(has_roles=has_roles)
    action = ActionFactory.create(plan=plan)
    admin = PersonFactory.create(general_admin_plans=[plan]).user
    assert admin is not None
    assert list(admin.get_editable_contact_person_roles(action)) == list(ActionContactPerson.get_roles())


def _edit_page(client, user, action: Action):
    client.force_login(user)
    response = client.get(edit_url(action))
    assert response.status_code == 200
    return response


def _contact_person_formsets(response) -> set[str]:
    return {name for name in response.context['form'].formsets if name.startswith('contact_persons')}


def test_moderator_cannot_edit_contact_persons_in_a_plan_without_roles(client):
    action = ActionFactory.create(plan=_plan(has_roles=False))
    moderator = _contact_person(action, Role.MODERATOR)
    editor = _contact_person(action, Role.EDITOR)
    assert moderator.person.user is not None

    response = _edit_page(client, moderator.person.user, action)

    assert _contact_person_formsets(response) == set()
    content = response.content.decode()
    # The contact persons are listed, but without the roles the plan doesn't use
    assert str(editor.person) in content
    read_only_labels = {label.strip() for label in re.findall(r'<div class="w-field__label">([^<]*)</div>', content)}
    assert read_only_labels.isdisjoint({str(Role.EDITOR.label), str(Role.MODERATOR.label)})


def test_plan_admin_edits_contact_persons_in_one_formset_in_a_plan_without_roles(client):
    plan = _plan(has_roles=False)
    action = ActionFactory.create(plan=plan)
    admin = PersonFactory.create(general_admin_plans=[plan]).user
    response = _edit_page(client, admin, action)
    assert _contact_person_formsets(response) == {'contact_persons'}


def test_moderator_edits_only_editors_in_a_plan_with_roles(client):
    action = ActionFactory.create(plan=_plan(has_roles=True))
    moderator = _contact_person(action, Role.MODERATOR)
    response = _edit_page(client, moderator.person.user, action)
    assert _contact_person_formsets(response) == {'contact_persons_editor'}


def test_field_customization_keeps_moderator_from_editing_contact_persons_in_a_plan_with_roles(client):
    plan = _plan(has_roles=True)
    BuiltInFieldCustomizationFactory.create(
        plan=plan,
        field_name='contact_persons',
        instances_editable_by=InstancesEditableByMixin.EditableBy.PLAN_ADMINS,
    )
    action = ActionFactory.create(plan=plan)
    moderator = _contact_person(action, Role.MODERATOR)
    response = _edit_page(client, moderator.person.user, action)
    assert _contact_person_formsets(response) == set()


def test_responsible_parties_stay_editable_for_contact_persons_in_a_plan_without_roles(client):
    action = ActionFactory.create(plan=_plan(has_roles=False))
    moderator = _contact_person(action, Role.MODERATOR)
    response = _edit_page(client, moderator.person.user, action)
    formsets = {name for name in response.context['form'].formsets if name.startswith('responsible_parties')}
    assert formsets == {'responsible_parties_collaborator'}


@pytest.mark.parametrize(('has_roles', 'status_code'), [(True, 200), (False, 400)])
def test_api_lets_moderator_add_editors_only_in_a_plan_with_roles(api_client, has_roles, status_code):
    plan = _plan(has_roles=has_roles)
    action = ActionFactory.create(plan=plan)
    moderator = _contact_person(action, Role.MODERATOR)
    new_person = PersonFactory.create(organization=plan.organization)
    api_client.force_login(moderator.person.user)
    url = reverse('action-detail', kwargs={'plan_pk': plan.pk, 'pk': action.pk})

    response = api_client.patch(
        url,
        data={
            'contact_persons': [
                {'person': moderator.person.pk, 'role': Role.MODERATOR},
                {'person': new_person.pk, 'role': Role.EDITOR},
            ]
        },
    )

    assert response.status_code == status_code, response.content


def _post_combined_contact_persons(client, user, action: Action, rows: list[tuple[int | None, int]]):
    """Post the edit form of a plan without roles, with one contact person row per `(row id, person id)`."""
    data: dict[str, object] = {
        'identifier': action.identifier,
        'name': action.name,
        'visibility': 'public',
        'contact_persons-TOTAL_FORMS': str(len(rows)),
        'contact_persons-INITIAL_FORMS': str(sum(1 for pk, _ in rows if pk is not None)),
        'contact_persons-MIN_NUM_FORMS': '0',
        'contact_persons-MAX_NUM_FORMS': '1000',
        'responsible_parties_primary-TOTAL_FORMS': '0',
        'responsible_parties_primary-INITIAL_FORMS': '0',
        'responsible_parties_collaborator-TOTAL_FORMS': '0',
        'responsible_parties_collaborator-INITIAL_FORMS': '0',
        'tasks-TOTAL_FORMS': '0',
        'tasks-INITIAL_FORMS': '0',
        'links-TOTAL_FORMS': '0',
        'links-INITIAL_FORMS': '0',
    }
    for i, (pk, person_pk) in enumerate(rows):
        data |= {
            f'contact_persons-{i}-id': pk or '',
            f'contact_persons-{i}-person': person_pk,
            f'contact_persons-{i}-ORDER': str(i + 1),
        }
    client.force_login(user)
    return client.post(edit_url(action), data=data)


def test_plan_admin_swaps_contact_persons_in_a_plan_without_roles(client):
    plan = _plan(has_roles=False)
    action = ActionFactory.create(plan=plan)
    admin = PersonFactory.create(general_admin_plans=[plan]).user
    first = _contact_person(action, Role.EDITOR)
    second = _contact_person(action, Role.MODERATOR)

    response = _post_combined_contact_persons(client, admin, action, [(first.pk, second.person.pk), (second.pk, first.person.pk)])

    assert response.status_code == 302
    assert list(action.contact_persons.values_list('person_id', flat=True)) == [second.person.pk, first.person.pk]


def test_contact_person_added_in_a_plan_without_roles_gets_the_default_role(client):
    plan = _plan(has_roles=False)
    action = ActionFactory.create(plan=plan)
    admin = PersonFactory.create(general_admin_plans=[plan]).user
    person = PersonFactory.create(organization=plan.organization)

    response = _post_combined_contact_persons(client, admin, action, [(None, person.pk)])

    assert response.status_code == 302
    assert action.contact_persons.get().role == Role.MODERATOR


@pytest.mark.parametrize(('has_roles', 'is_moderator'), [(True, False), (False, True)])
def test_editor_acts_as_moderator_only_in_a_plan_without_roles(has_roles, is_moderator):
    plan = _plan(has_roles=has_roles)
    workflow = WorkflowFactory.create()
    task = ActionModeratorApprovalTask.objects.create(name='Moderation', active=True)
    WorkflowTaskFactory.create(workflow=workflow, task=task)
    plan.features.moderation_workflow = workflow
    plan.features.save()
    action = ActionFactory.create(plan=plan)
    editor = _contact_person(action, Role.EDITOR)
    user = editor.person.user
    assert user is not None

    assert user._check_moderation_approve_permissions(action, editor.person) is is_moderator
    task_state = SimpleNamespace(workflow_state=SimpleNamespace(content_object=action), task=task)
    recipients = ActionModeratorApprovalTaskStateSubmissionEmailNotifier().get_recipient_users(task_state)
    assert (user in recipients) is is_moderator
    assert user.has_contact_person_role_for_action(Role.MODERATOR, action) is is_moderator
    restricted_field = BuiltInFieldCustomizationFactory.create(
        plan=plan, field_name='description', instances_visible_for=InstancesVisibleForMixin.VisibleFor.MODERATORS
    )
    assert restricted_field.is_instance_visible_for(user, plan, action) is is_moderator


@pytest.mark.parametrize('has_roles', [True, False])
def test_plan_can_hide_moderators_only_with_contact_person_roles(has_roles):
    features = _plan(has_roles=has_roles).features
    features.contact_persons_hide_moderators = True
    if has_roles:
        features.clean()
        return
    with pytest.raises(ValidationError):
        features.clean()
