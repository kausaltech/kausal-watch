from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

import pytest

from aplans.draft_references import strip_missing_references

from actions.action_admin import ActionAdmin
from actions.attributes import DraftAttributes
from actions.models import Action, ActionContactPerson
from actions.tests.factories import (
    ActionContactFactory,
    ActionDependencyRelationshipFactory,
    ActionDependencyRoleFactory,
    ActionFactory,
    ActionImpactFactory,
    ActionLinkFactory,
    ActionResponsiblePartyFactory,
    ActionTaskFactory,
    WorkflowFactory,
    WorkflowTaskFactory,
)
from admin_site.tests.factories import ClientPlanFactory
from indicators.tests.factories import ActionIndicatorFactory
from orgs.tests.factories import OrganizationFactory
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

if TYPE_CHECKING:
    from collections.abc import Callable

    import django.test.client
    from django.db.models import Model
    from wagtail.models import Workflow

    from actions.models import Plan
    from people.models import Person
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


def enable_moderation_workflow(plan: Plan) -> Workflow:
    workflow = WorkflowFactory.create()
    WorkflowTaskFactory.create(workflow=workflow)
    plan.features.moderation_workflow = workflow
    plan.features.save()
    return workflow


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


@pytest.mark.parametrize(('delete_dependent', 'expected_forms'), [(False, 1), (True, 0)])
def test_cascade_deleted_relationship_is_absent_from_the_dependencies_formset(
    plan_admin_user: User,
    action: Action,
    client: django.test.client.Client,
    delete_dependent: bool,
    expected_forms: int,
):
    """
    A relationship cascade-deleted with its dependent action does not reach the form.

    Unlike the other child relations, `dependent_relationships` is rendered as a formset, so a
    stale row would show up here as a hidden `id` the formset cannot resolve.
    """
    ClientPlanFactory.create(plan=action.plan)
    ActionDependencyRoleFactory.create(plan=action.plan)  # the panel is built only for a plan with roles
    enable_moderation_workflow(action.plan)
    relationship = ActionDependencyRelationshipFactory.create(preceding=action)
    action.save_revision()

    if delete_dependent:
        relationship.dependent.delete()  # cascades to the relationship

    edit_url = reverse(ActionAdmin().url_helper.get_action_url_name('edit'), kwargs={'instance_pk': action.pk})
    client.force_login(plan_admin_user)

    response = client.get(edit_url)

    assert response.status_code == 200
    formsets = response.context['form'].formsets
    assert 'dependent_relationships' in formsets
    assert formsets['dependent_relationships'].initial_form_count() == expected_forms


DRAFT_ACTIONS_QUERY = """
  query ($plan: ID!, $lang: String!) @locale(lang: $lang) @workflow(state: DRAFT) {
    planActions(plan: $plan) {
      name
      responsibleParties { organization { name } }
    }
  }
"""


def test_draft_listing_survives_a_deleted_organization(graphql_client_query, plan: Plan, person: Person, client):
    workflow = enable_moderation_workflow(plan)
    organization = OrganizationFactory.create()
    plan.related_organizations.add(organization)
    action = ActionFactory.create(plan=plan)
    ActionResponsiblePartyFactory.create(action=action, organization=organization)
    action.draft_attributes = DraftAttributes()
    action.save_revision(user=person.user)
    workflow.start(action, user=person.user)

    organization.delete()

    person.general_admin_plans.add(plan)
    person.save()
    client.force_login(person.user)
    response = graphql_client_query(DRAFT_ACTIONS_QUERY, variables={'plan': plan.identifier, 'lang': 'en'})

    assert 'errors' not in response
    assert response['data']['planActions'] == [{'name': action.name, 'responsibleParties': []}]


def test_strip_missing_references_nulls_what_it_can_and_drops_the_rest(plan: Plan):
    impact = ActionImpactFactory.create(plan=plan)
    action = ActionFactory.create(plan=plan, impact=impact)
    ActionContactFactory.create(action=action)
    task = ActionTaskFactory.create(action=action)
    task.completed_by = UserFactory.create()
    task.save()
    content = dict(action.save_revision().content)

    impact.delete()
    action.contact_persons.get().person.delete()
    task.completed_by.delete()

    strip_missing_references(Action, [content])

    assert content['impact'] is None  # the action can live without it
    assert content['contact_persons'] == []  # the row cannot live without its person
    assert [row['completed_by'] for row in content['tasks']] == [None]  # the task can
