from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

import pytest

from actions.action_admin import ActionAdmin
from actions.models import Action, ActionContactPerson
from actions.tests.factories import (
    ActionContactFactory,
    ActionDependencyRelationshipFactory,
    ActionFactory,
    ActionLinkFactory,
    ActionResponsiblePartyFactory,
    ActionTaskFactory,
    WorkflowFactory,
    WorkflowTaskFactory,
)
from admin_site.tests.factories import ClientPlanFactory
from indicators.tests.factories import ActionIndicatorFactory
from people.tests.factories import PersonFactory

if TYPE_CHECKING:
    from collections.abc import Callable

    import django.test.client
    from django.db.models import Model

    from actions.models import Plan
    from users.models import User

pytestmark = pytest.mark.django_db


def edit_post_data(action: Action, **overrides: object) -> dict[str, object]:
    """Return the fields the action edit form requires, with all formsets empty by default."""
    data: dict[str, object] = {
        'identifier': action.identifier,
        'name': action.name,
        'visibility': 'public',
        'contact_persons_moderator-TOTAL_FORMS': '0',
        'contact_persons_moderator-INITIAL_FORMS': '0',
        'contact_persons_editor-TOTAL_FORMS': '0',
        'contact_persons_editor-INITIAL_FORMS': '0',
        'responsible_parties_primary-TOTAL_FORMS': '0',
        'responsible_parties_primary-INITIAL_FORMS': '0',
        'responsible_parties_collaborator-TOTAL_FORMS': '0',
        'responsible_parties_collaborator-INITIAL_FORMS': '0',
        'tasks-TOTAL_FORMS': '0',
        'tasks-INITIAL_FORMS': '0',
        'links-TOTAL_FORMS': '0',
        'links-INITIAL_FORMS': '0',
    }
    return data | overrides


def enable_moderation_workflow(plan: Plan) -> None:
    workflow = WorkflowFactory.create()
    WorkflowTaskFactory.create(workflow=workflow)
    plan.features.moderation_workflow = workflow
    plan.features.save()


CHILD_RELATIONS: list[tuple[str, Callable[[Action], Model]]] = [
    ('contact_persons', lambda action: ActionContactFactory.create(action=action)),
    ('responsible_parties', lambda action: ActionResponsiblePartyFactory.create(action=action)),
    ('tasks', lambda action: ActionTaskFactory.create(action=action)),
    ('links', lambda action: ActionLinkFactory.create(action=action)),
    ('related_indicators', lambda action: ActionIndicatorFactory.create(action=action)),
    ('dependent_relationships', lambda action: ActionDependencyRelationshipFactory.create(preceding=action)),
]


@pytest.mark.parametrize(('relation', 'create_child'), CHILD_RELATIONS, ids=[relation for relation, _ in CHILD_RELATIONS])
def test_deleted_child_is_dereferenced_in_draft(plan: Plan, relation: str, create_child: Callable[[Action], Model]):
    action = ActionFactory.create(plan=plan)
    child = create_child(action)
    action.save_revision()

    child.delete()

    action.refresh_from_db()
    assert action.latest_revision is not None
    assert [item['pk'] for item in action.latest_revision.content[relation]] == [None]


def test_action_can_be_saved_after_contact_person_was_deleted(
    plan_admin_user: User, action: Action, client: django.test.client.Client
):
    ClientPlanFactory.create(plan=action.plan)
    enable_moderation_workflow(action.plan)
    person = PersonFactory.create(organization=action.plan.organization)
    contact_person = ActionContactFactory.create(action=action, person=person, role=ActionContactPerson.Role.MODERATOR)
    action.save_revision()

    # The contact person is removed from the published action, e.g. in the grid editor
    contact_person.delete()

    # Submit the edit form the way the edit view renders it, namely from the draft
    draft_contact_person = Action.objects.get(pk=action.pk).get_latest_revision_as_object().contact_persons.first()
    assert draft_contact_person is not None
    post_data = edit_post_data(
        action,
        **{
            'contact_persons_moderator-TOTAL_FORMS': '1',
            'contact_persons_moderator-INITIAL_FORMS': '1',
            'contact_persons_moderator-MIN_NUM_FORMS': '0',
            'contact_persons_moderator-MAX_NUM_FORMS': '1000',
            'contact_persons_moderator-0-id': draft_contact_person.pk or '',
            'contact_persons_moderator-0-person': person.pk,
            'contact_persons_moderator-0-ORDER': '1',
        },
    )
    edit_url = reverse(ActionAdmin().url_helper.get_action_url_name('edit'), kwargs={'instance_pk': action.pk})
    client.force_login(plan_admin_user)

    response = client.post(edit_url, data=post_data)

    assert response.status_code == 302
    new_draft = Action.objects.get(pk=action.pk).get_latest_revision_as_object()
    assert [cp.person_id for cp in new_draft.contact_persons.all()] == [person.pk]


def test_action_can_be_saved_after_child_was_cascade_deleted(
    plan_admin_user: User, action: Action, client: django.test.client.Client
):
    """
    A child deleted through its other parent leaves the draft publishable.

    Modelcluster deserializes child objects with `strict_fks=True`, so a row whose
    foreign key no longer resolves is dropped instead of reaching the form.
    """
    ClientPlanFactory.create(plan=action.plan)
    enable_moderation_workflow(action.plan)
    action_indicator = ActionIndicatorFactory.create(action=action)
    action.save_revision()

    action_indicator.indicator.delete()  # cascades to the link between the action and the indicator

    draft = Action.objects.get(pk=action.pk).get_latest_revision_as_object()
    assert list(draft.related_indicators.all()) == []
    edit_url = reverse(ActionAdmin().url_helper.get_action_url_name('edit'), kwargs={'instance_pk': action.pk})
    client.force_login(plan_admin_user)

    response = client.post(edit_url, data=edit_post_data(action))

    assert response.status_code == 302
    new_draft = Action.objects.get(pk=action.pk).get_latest_revision_as_object()
    assert list(new_draft.related_indicators.all()) == []
