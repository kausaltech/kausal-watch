"""
Phase-0 spike for P-2081: task-level responsible parties and contact persons.

The open question is not the data model but the admin form: `ActionTask` rows are edited in a
formset nested in the action edit form, so assignments live in a *grandchild* formset, and
`ActionEditHandler`/`ActionAdminForm` rebuild and reorder formsets by hand. These tests exercise
the real edit view and the real draft round-trip rather than the models in isolation.
"""

from __future__ import annotations

import datetime

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.db.utils import IntegrityError
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest

from aplans.cache import PlanSpecificCache
from aplans.context_vars import ctx_instance, ctx_request
from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin

from actions.action_admin import ActionAdmin, ReadOnlyInlinePanel
from actions.models import Action
from actions.models.action import ActionContactPerson, ActionTask, ActionTaskContactPerson, ActionTaskResponsibleParty
from actions.models.features import PlanFeatures
from actions.perms import get_action_contact_person_perms
from actions.tests.factories import (
    ActionTaskContactFactory,
    ActionTaskFactory,
    ActionTaskResponsiblePartyFactory,
)
from admin_site.field_customization import get_customizable_field_names
from admin_site.models import BuiltInFieldCustomization
from admin_site.tests.factories import BuiltInFieldCustomizationFactory, ClientPlanFactory
from orgs.models import Organization
from orgs.tests.factories import OrganizationFactory
from people.models import Person
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db


def _edit_url(action: Action) -> str:
    return reverse(ActionAdmin().url_helper.get_action_url_name('edit'), kwargs={'instance_pk': action.pk})


def _base_post_data(action: Action) -> dict[str, str]:
    """Build the minimum an action edit POST needs: every formset the form declares, empty."""
    return {
        'identifier': action.identifier,
        'name': action.name,
        'visibility': 'public',
        'links-TOTAL_FORMS': '0',
        'links-INITIAL_FORMS': '0',
        'contact_persons_editor-TOTAL_FORMS': '0',
        'contact_persons_editor-INITIAL_FORMS': '0',
        'contact_persons_moderator-TOTAL_FORMS': '0',
        'contact_persons_moderator-INITIAL_FORMS': '0',
        'responsible_parties_primary-TOTAL_FORMS': '0',
        'responsible_parties_primary-INITIAL_FORMS': '0',
        'responsible_parties_collaborator-TOTAL_FORMS': '0',
        'responsible_parties_collaborator-INITIAL_FORMS': '0',
        'tasks-TOTAL_FORMS': '0',
        'tasks-INITIAL_FORMS': '0',
    }


def _form_class(rf, user, action):
    request = rf.get('/')
    request.user = user
    request.admin_cache = PlanSpecificCache(plan=action.plan)
    request.get_active_admin_plan = lambda: action.plan
    with ctx_request.activate(request), ctx_instance.activate(action):
        edit_handler = ActionAdmin().get_edit_handler()
        return edit_handler.bind_to_model(Action).get_form_class()


def test_nested_formsets_are_declared_on_the_task_child_form(rf, action, plan_admin_user):
    """The grandchild formsets must reach the task form class, not just the panel definition."""
    form_class = _form_class(rf, plan_admin_user, action)

    tasks_formset = form_class.formsets['tasks']
    nested = tasks_formset.form.formsets

    assert set(nested) == {'responsible_parties', 'contact_persons'}


def test_admin_post_creates_task_with_assignments(client, action, plan_admin_user):
    ClientPlanFactory.create(plan=action.plan)
    organization = OrganizationFactory.create()
    action.plan.related_organizations.add(organization)
    person = PersonFactory.create(organization=action.plan.organization)
    client.force_login(plan_admin_user)

    post_data = _base_post_data(action) | {
        'tasks-TOTAL_FORMS': '1',
        'tasks-INITIAL_FORMS': '0',
        'tasks-0-name': 'Spike task',
        'tasks-0-due_at': '2027-01-01',
        'tasks-0-state': ActionTask.NOT_STARTED,
        'tasks-0-responsible_parties-TOTAL_FORMS': '1',
        'tasks-0-responsible_parties-INITIAL_FORMS': '0',
        'tasks-0-responsible_parties-0-organization': str(organization.pk),
        'tasks-0-contact_persons-TOTAL_FORMS': '1',
        'tasks-0-contact_persons-INITIAL_FORMS': '0',
        'tasks-0-contact_persons-0-person': str(person.pk),
    }

    response = client.post(_edit_url(action), data=post_data)

    assert response.status_code == 302, getattr(response, 'context_data', None)
    task = action.tasks.get()
    assert task.name == 'Spike task'
    assert [rp.organization for rp in task.responsible_parties.all()] == [organization]
    assert [cp.person for cp in task.contact_persons.all()] == [person]


def test_admin_post_edits_assignments_of_an_existing_task(client, action, plan_admin_user):
    ClientPlanFactory.create(plan=action.plan)
    task = ActionTaskFactory.create(action=action)
    org_a = OrganizationFactory.create()
    org_b = OrganizationFactory.create()
    action.plan.related_organizations.add(org_a, org_b)
    assignment = ActionTaskResponsibleParty.objects.create(task=task, organization=org_a)
    client.force_login(plan_admin_user)

    post_data = _base_post_data(action) | {
        'tasks-TOTAL_FORMS': '1',
        'tasks-INITIAL_FORMS': '1',
        'tasks-0-id': str(task.pk),
        'tasks-0-name': task.name,
        'tasks-0-due_at': task.due_at.isoformat(),
        'tasks-0-state': task.state,
        'tasks-0-responsible_parties-TOTAL_FORMS': '1',
        'tasks-0-responsible_parties-INITIAL_FORMS': '1',
        'tasks-0-responsible_parties-0-id': str(assignment.pk),
        'tasks-0-responsible_parties-0-organization': str(org_b.pk),
        'tasks-0-contact_persons-TOTAL_FORMS': '0',
        'tasks-0-contact_persons-INITIAL_FORMS': '0',
    }

    response = client.post(_edit_url(action), data=post_data)

    assert response.status_code == 302, getattr(response, 'context_data', None)
    assert [rp.organization for rp in task.responsible_parties.all()] == [org_b]


def test_draft_round_trip_keeps_task_assignments(action):
    """
    The reason `ActionTask` has to be clusterable: assignments must survive draft serialization.

    This is the check that fails silently if `ActionTask` stays a plain model — the nested rows
    are dropped from the revision content without an error.
    """
    organization = OrganizationFactory.create()
    person = PersonFactory.create(organization=action.plan.organization)
    task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
    ActionTaskResponsibleParty.objects.create(task=task, organization=organization)
    ActionTaskContactPerson.objects.create(task=task, person=person)

    action.refresh_from_db()
    data = action.serializable_data()

    serialized_task = data['tasks'][0]
    assert [rp['organization'] for rp in serialized_task['responsible_parties']] == [organization.pk]
    assert [cp['person'] for cp in serialized_task['contact_persons']] == [person.pk]

    restored = Action.from_serializable_data(data)
    assert restored is not None
    restored_task = restored.tasks.all()[0]
    assert [rp.organization_id for rp in restored_task.responsible_parties.all()] == [organization.pk]
    assert [cp.person_id for cp in restored_task.contact_persons.all()] == [person.pk]


def test_draft_publish_keeps_task_assignments(action, plan_admin_user):
    """
    Publish a draft whose task carries an assignment and check the row lands in the database.

    The revision is built the way the admin does it — from `serializable_data()` of the in-memory
    cluster — with the `attributes` key `Action.publish()` requires added the same way the existing
    admin tests do it.
    """
    from wagtail.models import Revision

    organization = OrganizationFactory.create()
    task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
    action.refresh_from_db()

    # Assign through the cluster (not a throwaway queryset instance) so the change is in memory only.
    draft_task = action.tasks.all()[0]
    draft_task.responsible_parties = [ActionTaskResponsibleParty(organization=organization)]
    action.tasks = [draft_task]
    content = action.serializable_data()
    assert [rp['organization'] for rp in content['tasks'][0]['responsible_parties']] == [organization.pk]
    content.setdefault('attributes', {})
    assert not ActionTaskResponsibleParty.objects.filter(task=task).exists(), 'draft must not write through'

    base_revision = action.save_revision(user=plan_admin_user)
    revision: Revision = Revision(
        content_type=base_revision.content_type,
        base_content_type=base_revision.base_content_type,
        object_id=str(action.pk),
    )
    revision.content = content
    revision.save()

    revision.publish(user=plan_admin_user)

    assert [rp.organization for rp in task.responsible_parties.all()] == [organization]


def _customize(plan, field_name: str, *, visible_for, editable_by) -> None:
    BuiltInFieldCustomizationFactory.create(
        plan=plan,
        content_type=ContentType.objects.get(app_label='actions', model='actiontask'),
        field_name=field_name,
        instances_visible_for=visible_for,
        instances_editable_by=editable_by,
    )


def test_assignment_relations_are_registered_as_customizable():
    """Plan admins can only restrict a field that is registered; InlinePanels are not collected automatically."""
    customizable = get_customizable_field_names(ActionTask)

    assert 'responsible_parties' in customizable
    assert 'contact_persons' in customizable


def test_assignment_panels_are_hidden_for_a_restricted_user(rf, action, action_contact_person_user):
    _customize(
        action.plan,
        'responsible_parties',
        visible_for=InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
        editable_by=InstancesEditableByMixin.EditableBy.NOT_EDITABLE,
    )

    nested = _form_class(rf, action_contact_person_user, action).formsets['tasks'].form.formsets

    assert 'responsible_parties' not in nested, 'a hidden relation must not be editable either'
    assert 'contact_persons' in nested


def test_hidden_relation_stays_hidden_with_default_editability(rf, action, action_contact_person_user):
    """
    `editable_by` defaults to "authenticated", so a visibility-only restriction yields (False, True).

    Reading the flags independently — or letting editability imply visibility, as the action-level
    panels do — would leave the panel visible and editable for exactly the user it was hidden from.
    """
    _customize(
        action.plan,
        'responsible_parties',
        visible_for=InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
        editable_by=InstancesEditableByMixin.EditableBy.AUTHENTICATED,
    )

    is_visible, is_editable = BuiltInFieldCustomization.get_field_access(
        action_contact_person_user, action.plan, ActionTask, 'responsible_parties', action
    )
    assert (is_visible, is_editable) == (False, True), 'the case under test must actually be (False, True)'

    nested = _form_class(rf, action_contact_person_user, action).formsets['tasks'].form.formsets
    assert 'responsible_parties' not in nested


def test_visible_but_not_editable_relation_is_read_only(rf, action, action_contact_person_user):
    """A relation that is public but only editable by plan admins must render without form inputs."""
    _customize(
        action.plan,
        'responsible_parties',
        visible_for=InstancesVisibleForMixin.VisibleFor.PUBLIC,
        editable_by=InstancesEditableByMixin.EditableBy.PLAN_ADMINS,
    )

    is_visible, is_editable = BuiltInFieldCustomization.get_field_access(
        action_contact_person_user, action.plan, ActionTask, 'responsible_parties', action
    )
    assert (is_visible, is_editable) == (True, False), 'the case under test must actually be (True, False)'

    admin = ActionAdmin()
    plan = action.plan
    panels = admin.get_task_panels(action_contact_person_user, plan, action)
    by_relation = {getattr(p, 'relation_name', None): p for p in panels}
    assert isinstance(by_relation['responsible_parties'], ReadOnlyInlinePanel)

    nested = _form_class(rf, action_contact_person_user, action).formsets['tasks'].form.formsets
    assert 'responsible_parties' not in nested, 'a read-only relation must not get an editable formset'


@pytest.mark.parametrize(
    ('visible_for', 'editable_by'),
    [
        (InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS, InstancesEditableByMixin.EditableBy.AUTHENTICATED),
        (InstancesVisibleForMixin.VisibleFor.PUBLIC, InstancesEditableByMixin.EditableBy.PLAN_ADMINS),
    ],
    ids=['hidden-but-default-editable', 'visible-but-read-only'],
)
def test_restricted_relation_cannot_be_written_by_posting(client, action, action_contact_person_user, visible_for, editable_by):
    """The real guarantee: posted assignment data is ignored when the user may not edit the relation."""
    ClientPlanFactory.create(plan=action.plan)
    organization = OrganizationFactory.create()
    task = ActionTaskFactory.create(action=action)
    _customize(action.plan, 'responsible_parties', visible_for=visible_for, editable_by=editable_by)
    client.force_login(action_contact_person_user)

    post_data = _base_post_data(action) | {
        'tasks-TOTAL_FORMS': '1',
        'tasks-INITIAL_FORMS': '1',
        'tasks-0-id': str(task.pk),
        'tasks-0-name': task.name,
        'tasks-0-due_at': task.due_at.isoformat(),
        'tasks-0-state': task.state,
        'tasks-0-responsible_parties-TOTAL_FORMS': '1',
        'tasks-0-responsible_parties-INITIAL_FORMS': '0',
        'tasks-0-responsible_parties-0-organization': str(organization.pk),
        'tasks-0-contact_persons-TOTAL_FORMS': '0',
        'tasks-0-contact_persons-INITIAL_FORMS': '0',
    }

    response = client.post(_edit_url(action), data=post_data)

    assert response.status_code == 302, getattr(response, 'context_data', None)
    assert list(task.responsible_parties.all()) == []


def test_a_plan_admin_sees_a_relation_hidden_from_others_but_read_only_if_not_editable(rf, action, plan_admin_user):
    """`NOT_EDITABLE` excludes plan admins too (only superusers are exempt), so they get the read-only panel."""
    _customize(
        action.plan,
        'responsible_parties',
        visible_for=InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
        editable_by=InstancesEditableByMixin.EditableBy.NOT_EDITABLE,
    )

    panels = {getattr(p, 'relation_name', None): p for p in ActionAdmin().get_task_panels(plan_admin_user, action.plan, action)}
    assert isinstance(panels['responsible_parties'], ReadOnlyInlinePanel)

    nested = _form_class(rf, plan_admin_user, action).formsets['tasks'].form.formsets
    assert 'responsible_parties' not in nested


def test_assignment_panels_stay_editable_for_a_plan_admin(rf, action, plan_admin_user, action_contact_person_user):
    """Restricting a relation to plan admins leaves them the editable panel and takes it from everyone else."""
    _customize(
        action.plan,
        'responsible_parties',
        visible_for=InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
        editable_by=InstancesEditableByMixin.EditableBy.PLAN_ADMINS,
    )

    assert 'responsible_parties' in _form_class(rf, plan_admin_user, action).formsets['tasks'].form.formsets
    assert 'responsible_parties' not in _form_class(rf, action_contact_person_user, action).formsets['tasks'].form.formsets


def test_action_contact_person_can_save_assignments(client, action, action_contact_person_user):
    """A contact person may edit tasks, so they must hold the permissions for the assignment rows too."""
    ClientPlanFactory.create(plan=action.plan)
    organization = OrganizationFactory.create()
    action.plan.related_organizations.add(organization)
    client.force_login(action_contact_person_user)

    post_data = _base_post_data(action) | {
        'tasks-TOTAL_FORMS': '1',
        'tasks-INITIAL_FORMS': '0',
        'tasks-0-name': 'Contact person task',
        'tasks-0-due_at': '2027-01-01',
        'tasks-0-state': ActionTask.NOT_STARTED,
        'tasks-0-responsible_parties-TOTAL_FORMS': '1',
        'tasks-0-responsible_parties-INITIAL_FORMS': '0',
        'tasks-0-responsible_parties-0-organization': str(organization.pk),
        'tasks-0-contact_persons-TOTAL_FORMS': '0',
        'tasks-0-contact_persons-INITIAL_FORMS': '0',
    }

    response = client.post(_edit_url(action), data=post_data)

    assert response.status_code == 302, getattr(response, 'context_data', None)
    task = action.tasks.get()
    assert [rp.organization for rp in task.responsible_parties.all()] == [organization]


def test_contact_person_permissions_cover_the_assignment_models():
    codenames = {p.codename for p in get_action_contact_person_perms()}

    for model in ('actiontaskresponsibleparty', 'actiontaskcontactperson'):
        for op in ('add', 'change', 'delete'):
            assert f'{op}_{model}' in codenames


def test_deleting_an_assignment_repairs_the_draft(action, plan_admin_user):
    """A draft referencing a deleted grandchild pk must not block publishing."""
    from wagtail.models import Revision

    organization = OrganizationFactory.create()
    task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
    assignment = ActionTaskResponsibleParty.objects.create(task=task, organization=organization)
    action.refresh_from_db()

    content = action.serializable_data()
    content.setdefault('attributes', {})
    base_revision = action.save_revision(user=plan_admin_user)
    revision: Revision = Revision(
        content_type=base_revision.content_type,
        base_content_type=base_revision.base_content_type,
        object_id=str(action.pk),
    )
    revision.content = content
    revision.save()
    action.latest_revision = revision
    action.save(update_fields=['latest_revision'])
    assert [rp['pk'] for rp in revision.content['tasks'][0]['responsible_parties']] == [assignment.pk]

    assignment.delete()

    revision.refresh_from_db()
    assert [rp['pk'] for rp in revision.content['tasks'][0]['responsible_parties']] == [None]
    revision.publish(user=plan_admin_user)
    assert [rp.organization for rp in task.responsible_parties.all()] == [organization]


def test_graphql_exposes_assignments(graphql_client_query_data, action, plan_admin_user):
    organization = OrganizationFactory.create()
    person = PersonFactory.create(organization=action.plan.organization)
    task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
    ActionTaskResponsibleParty.objects.create(task=task, organization=organization)
    ActionTaskContactPerson.objects.create(task=task, person=person)

    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planActions(plan: $plan) {
            tasks {
              responsibleParties { organization { name } }
              contactPersons { person { firstName } }
            }
          }
        }
        """,
        variables={'plan': action.plan.identifier},
    )

    tasks = [t for a in data['planActions'] for t in a['tasks']]
    assert tasks[0]['responsibleParties'] == [{'organization': {'name': organization.name}}]
    assert tasks[0]['contactPersons'] == [{'person': {'firstName': person.first_name}}]


def test_graphql_redacts_task_contact_persons(graphql_client_query_data, action):
    person = PersonFactory.create(organization=action.plan.organization)
    task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
    ActionTaskContactPerson.objects.create(task=task, person=person)
    action.plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.NONE
    action.plan.features.save()

    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planActions(plan: $plan) {
            tasks { contactPersons { person { firstName } } }
          }
        }
        """,
        variables={'plan': action.plan.identifier},
    )

    tasks = [t for a in data['planActions'] for t in a['tasks']]
    assert tasks[0]['contactPersons'] == []


def test_read_only_relation_lists_its_rows(rf, action, action_contact_person_user):
    """
    The read-only panel must actually show the assignments, not just replace the editable panel.

    The panel is exercised directly: rendering the whole edit page needs a built staticfiles manifest,
    which this environment does not have (the same reason `test_admin.py::test_action_admin` fails here).
    """
    organization = OrganizationFactory.create(name='Read-only department')
    task = ActionTaskFactory.create(action=action)
    ActionTaskResponsibleParty.objects.create(task=task, organization=organization)
    request = rf.get('/')
    request.user = action_contact_person_user

    panel = ReadOnlyInlinePanel('responsible_parties', heading='Responsible parties').bind_to_model(ActionTask)
    bound = panel.get_bound_panel(instance=task, request=request, form=None)

    assert [item['value'] for item in bound.get_context_data()['items']] == ['Read-only department']


def _chooser_names(client, url_name: str) -> str:
    return client.get(reverse(url_name)).content.decode()


def test_task_person_chooser_offers_contact_persons_from_unrelated_organizations(client, action, plan_admin_user):
    """The "external consultant" case: a plan contact person whose organization is unrelated to the plan."""
    consultant = PersonFactory.create(first_name='Xenia', last_name='Consultant')
    assert consultant.organization not in action.plan.related_organizations.all()
    ActionContactPerson.objects.create(action=action, person=consultant)
    client.force_login(plan_admin_user)

    assert 'Xenia' in _chooser_names(client, 'task_person_chooser:choose')


def test_the_shared_person_chooser_is_left_alone(client, action, plan_admin_user):
    """Widening task assignment must not widen the four other fields that share `PersonChooser`."""
    consultant = PersonFactory.create(first_name='Xenia', last_name='Consultant')
    ActionContactPerson.objects.create(action=action, person=consultant)
    client.force_login(plan_admin_user)

    assert 'Xenia' not in _chooser_names(client, 'person_chooser:choose')


def test_task_person_chooser_still_excludes_people_outside_the_plan(client, action, plan_admin_user):
    """Widening the list must not turn it into "every person in the database"."""
    PersonFactory.create(first_name='Unrelated', last_name='Stranger')
    client.force_login(plan_admin_user)

    assert 'Unrelated' not in _chooser_names(client, 'task_person_chooser:choose')


def test_an_organization_cannot_be_assigned_to_the_same_task_twice(action):
    task = ActionTaskFactory.create(action=action)
    assignment = ActionTaskResponsiblePartyFactory.create(task=task)

    with pytest.raises(IntegrityError):
        ActionTaskResponsiblePartyFactory.create(task=task, organization=assignment.organization)


def test_a_person_cannot_be_assigned_to_the_same_task_twice(action):
    task = ActionTaskFactory.create(action=action)
    assignment = ActionTaskContactFactory.create(task=task)

    with pytest.raises(IntegrityError):
        ActionTaskContactFactory.create(task=task, person=assignment.person)


def test_the_same_organization_can_be_assigned_to_two_tasks(action):
    organization = OrganizationFactory.create()
    first = ActionTaskResponsiblePartyFactory.create(task__action=action, organization=organization)
    second = ActionTaskResponsiblePartyFactory.create(task__action=action, organization=organization)

    assert first.task != second.task


@pytest.mark.parametrize('deleted', ['task', 'assignee'])
def test_assignments_are_removed_with_either_end(action, deleted):
    assignment = ActionTaskResponsiblePartyFactory.create(task__action=action)

    if deleted == 'task':
        assignment.task.delete()
    else:
        assignment.organization.delete()

    assert not ActionTaskResponsibleParty.objects.filter(pk=assignment.pk).exists()


def test_deleting_an_action_removes_its_task_assignments(action):
    assignment = ActionTaskResponsiblePartyFactory.create(task__action=action)
    person_assignment = ActionTaskContactFactory.create(task=assignment.task)

    action.delete()

    assert not ActionTaskResponsibleParty.objects.filter(pk=assignment.pk).exists()
    assert not ActionTaskContactPerson.objects.filter(pk=person_assignment.pk).exists()


def test_graphql_redacts_task_contact_persons_to_name_only(graphql_client_query_data, action):
    """At the `NAME` level the person is listed, but only with the fields `get_redacted_copy()` keeps."""
    person = PersonFactory.create(organization=action.plan.organization, email='secret@example.com')
    task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
    ActionTaskContactFactory.create(task=task, person=person)
    action.plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.NAME
    action.plan.features.save()

    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          planActions(plan: $plan) {
            tasks { contactPersons { person { firstName email } } }
          }
        }
        """,
        variables={'plan': action.plan.identifier},
    )

    tasks = [t for a in data['planActions'] for t in a['tasks']]
    (contact,) = tasks[0]['contactPersons']
    assert contact['person']['firstName'] == person.first_name
    assert not contact['person']['email'], 'the email must not survive NAME-level redaction'


def _query_count_for_plan(graphql_client_query_data, plan) -> int:
    query = """
        query($plan: ID!) {
          planActions(plan: $plan) {
            tasks {
              responsibleParties { organization { name } }
              contactPersons { person { firstName } }
            }
          }
        }
    """
    with CaptureQueriesContext(connection) as ctx:
        data = graphql_client_query_data(query, variables={'plan': plan.identifier})
    tasks = [t for a in data['planActions'] for t in a['tasks']]
    assert tasks
    assert all(t['responsibleParties'] for t in tasks)
    assert all(t['contactPersons'] for t in tasks)
    return len(ctx)


def test_redaction_does_not_add_a_query_per_assignment(graphql_client_query_data, plan_factory, action_factory):
    """
    The `NAME` level must not re-read each person from the database.

    The redaction branch only runs below `ALL`, so the general query-count test never reaches it; reading
    `atcp.person` again there instead of the person already resolved from the cache made a plan-actions
    query scale with the number of assignments rather than the number of tasks.
    """
    plan = _plan_with_tasks(plan_factory, action_factory, 2)
    plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.NAME
    plan.features.save()
    larger = _plan_with_tasks(plan_factory, action_factory, 6)
    larger.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.NAME
    larger.features.save()

    small_count = _query_count_for_plan(graphql_client_query_data, plan)
    large_count = _query_count_for_plan(graphql_client_query_data, larger)

    assert large_count - small_count <= 6 - 2, (
        f'{large_count} queries for 6 tasks vs {small_count} for 2 at the NAME level'
    )


def _plan_with_tasks(plan_factory, action_factory, task_count: int):
    plan = plan_factory()
    action = action_factory(plan=plan)
    for _i in range(task_count):
        task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
        ActionTaskResponsiblePartyFactory.create(task=task)
        ActionTaskContactFactory.create(task=task)
    return plan


def test_graphql_task_assignments_cost_at_most_one_query_per_task(graphql_client_query_data, plan_factory, action_factory):
    """
    Pin the known query cost of task assignments: one query per task, and nothing worse.

    Responsible parties are prefetched and cost nothing per task. Contact persons cost one query each,
    because `ActionTaskNode.resolve_contact_persons` is a custom resolver (it applies the privacy
    redaction) and graphene-django-optimizer does not apply a nested type's prefetch hints to one — the
    relation is fetched per task no matter which hint form is used. Removing the custom resolver removes
    the per-task query entirely, which is the measurement behind the two options recorded in the plan.

    A budget of zero extra queries is the goal; this test exists so the cost cannot quietly grow past one
    per task (it was two before the person FK was served from the plan cache).
    """
    task_counts = (2, 8)
    small = _plan_with_tasks(plan_factory, action_factory, task_counts[0])
    large = _plan_with_tasks(plan_factory, action_factory, task_counts[1])

    small_count = _query_count_for_plan(graphql_client_query_data, small)
    large_count = _query_count_for_plan(graphql_client_query_data, large)

    extra_tasks = task_counts[1] - task_counts[0]
    assert large_count - small_count <= extra_tasks, (
        f'{large_count} queries for {task_counts[1]} tasks vs {small_count} for {task_counts[0]}: more than one query per task'
    )


def test_cross_plan_task_contacts_use_their_own_plans_privacy_setting(
    graphql_client_query_data, plan, plan_factory, action_factory
):
    """
    `relatedPlanActions(plan: A)` returns plan B's actions while the query context still holds A.

    Redaction has to follow the plan that owns the task, not the one that was queried: otherwise a
    permissive plan publishes the contact details of a restrictive plan it happens to be related to.
    """
    other_plan = plan_factory()
    plan.related_plans.add(other_plan)
    plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.ALL
    plan.features.save()
    other_plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.NONE
    other_plan.features.save()

    other_action = action_factory(plan=other_plan)
    task = ActionTaskFactory.create(action=other_action, due_at=datetime.date(2027, 1, 1))
    ActionTaskContactFactory.create(task=task, person=PersonFactory.create(organization=other_plan.organization))

    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          relatedPlanActions(plan: $plan) { tasks { contactPersons { person { firstName } } } }
        }
        """,
        variables={'plan': plan.identifier},
    )

    tasks = [t for a in data['relatedPlanActions'] for t in a['tasks']]
    assert tasks, "the related plan's task should be in the result"
    assert all(t['contactPersons'] == [] for t in tasks), 'the other plan hides contact persons'


@pytest.mark.parametrize(
    ('relation', 'field', 'make_outsider'),
    [
        ('contact_persons', 'person', lambda: PersonFactory.create(organization=OrganizationFactory.create())),
        ('responsible_parties', 'organization', OrganizationFactory.create),
    ],
)
def test_assignees_from_outside_the_plan_are_rejected(rf, action, plan_admin_user, relation, field, make_outsider):
    """
    The chooser only filters what is offered; the posted id has to be rejected server-side.

    Otherwise an editor can assign another tenant's person or organization by posting its id, and the
    task API then publishes it under this plan's privacy settings.

    The form is validated directly rather than through the edit view, because re-rendering an invalid
    action form needs a built staticfiles manifest that this environment does not have.
    """
    outsider = make_outsider()
    if relation == 'contact_persons':
        assert outsider not in Person.objects.available_for_plan(action.plan, include_contact_persons=True)
    else:
        assert outsider not in Organization.objects.available_for_plan(action.plan)

    data = _base_post_data(action) | {
        'tasks-TOTAL_FORMS': '1',
        'tasks-INITIAL_FORMS': '0',
        'tasks-0-name': 'Task with an outsider',
        'tasks-0-due_at': '2027-01-01',
        'tasks-0-state': ActionTask.NOT_STARTED,
        'tasks-0-responsible_parties-TOTAL_FORMS': '0',
        'tasks-0-responsible_parties-INITIAL_FORMS': '0',
        'tasks-0-contact_persons-TOTAL_FORMS': '0',
        'tasks-0-contact_persons-INITIAL_FORMS': '0',
        f'tasks-0-{relation}-TOTAL_FORMS': '1',
        f'tasks-0-{relation}-0-{field}': str(outsider.pk),
    }

    form = _form_class(rf, plan_admin_user, action)(data=data, instance=action)

    assert not form.is_valid(), 'an assignee from outside the plan must not validate'
    child_form = form.formsets['tasks'].forms[0].formsets[relation].forms[0]
    assert field in child_form.errors


@pytest.mark.parametrize(
    ('relation', 'field'),
    [('contact_persons', 'person'), ('responsible_parties', 'organization')],
)
def test_assignees_from_the_plan_still_validate(rf, action, plan_admin_user, relation, field):
    """The counterpart to the rejection above: the plan's own people and organizations are accepted."""
    if relation == 'contact_persons':
        insider = PersonFactory.create(organization=action.plan.organization)
    else:
        insider = OrganizationFactory.create()
        action.plan.related_organizations.add(insider)

    data = _base_post_data(action) | {
        'tasks-TOTAL_FORMS': '1',
        'tasks-INITIAL_FORMS': '0',
        'tasks-0-name': 'Task with an insider',
        'tasks-0-due_at': '2027-01-01',
        'tasks-0-state': ActionTask.NOT_STARTED,
        'tasks-0-responsible_parties-TOTAL_FORMS': '0',
        'tasks-0-responsible_parties-INITIAL_FORMS': '0',
        'tasks-0-contact_persons-TOTAL_FORMS': '0',
        'tasks-0-contact_persons-INITIAL_FORMS': '0',
        f'tasks-0-{relation}-TOTAL_FORMS': '1',
        f'tasks-0-{relation}-0-{field}': str(insider.pk),
    }

    form = _form_class(rf, plan_admin_user, action)(data=data, instance=action)

    assert form.is_valid(), form.formsets['tasks'].forms[0].formsets[relation].forms[0].errors


def test_publishing_a_draft_that_swaps_two_task_assignees(action, plan_admin_user):
    """
    Swapping the organizations of two existing assignment rows must not break publishing.

    Saving the rows one by one hits the `(task, organization)` unique constraint halfway through, which
    is why `Action.publish()` renormalizes the primary keys first — the task-level rows need the same
    treatment as the action-level ones.
    """
    from wagtail.models import Revision

    org_a = OrganizationFactory.create()
    org_b = OrganizationFactory.create()
    task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
    first = ActionTaskResponsiblePartyFactory.create(task=task, organization=org_a)
    second = ActionTaskResponsiblePartyFactory.create(task=task, organization=org_b)
    action.refresh_from_db()

    content = action.serializable_data()
    content.setdefault('attributes', {})
    parties = content['tasks'][0]['responsible_parties']
    by_pk = {party['pk']: party for party in parties}
    by_pk[first.pk]['organization'] = org_b.pk
    by_pk[second.pk]['organization'] = org_a.pk

    base_revision = action.save_revision(user=plan_admin_user)
    revision: Revision = Revision(
        content_type=base_revision.content_type,
        base_content_type=base_revision.base_content_type,
        object_id=str(action.pk),
    )
    revision.content = content
    revision.save()
    action.latest_revision = revision
    action.save(update_fields=['latest_revision'])

    revision.publish(user=plan_admin_user)

    assert {rp.organization_id for rp in task.responsible_parties.all()} == {org_a.pk, org_b.pk}


def test_rest_api_identifies_the_assignees(api_client, plan, action, action_task_list_url):
    """
    The REST fields have to name the organization and the person.

    Serializing the join rows' own primary keys would identify nothing: those models have no endpoint.
    """
    organization = OrganizationFactory.create()
    person = PersonFactory.create(organization=plan.organization)
    task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
    ActionTaskResponsiblePartyFactory.create(task=task, organization=organization)
    ActionTaskContactFactory.create(task=task, person=person)

    response = api_client.get(action_task_list_url)

    assert response.status_code == 200
    (payload,) = [t for t in response.json()['results'] if t['id'] == task.pk]
    assert [rp['organization'] for rp in payload['responsible_parties']] == [organization.pk]
    assert [cp['person'] for cp in payload['contact_persons']] == [person.pk]


def test_rest_api_hides_task_contact_persons_when_the_plan_does(api_client, plan, action, action_task_list_url):
    """The list endpoint is public, so it follows the same `NONE` rule as GraphQL."""
    task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
    ActionTaskContactFactory.create(task=task)
    plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.NONE
    plan.features.save()

    response = api_client.get(action_task_list_url)

    assert response.status_code == 200
    (payload,) = [t for t in response.json()['results'] if t['id'] == task.pk]
    assert payload['contact_persons'] == []


def test_rest_api_hides_task_contact_persons_from_anonymous_callers_when_authenticated_only(
    api_client, plan, action, action_task_list_url
):
    """
    `ALL_FOR_AUTHENTICATED` hides contact persons from anonymous callers, and the list endpoint is public.

    `PlanFeatures.public_contact_persons` is false for this setting exactly as it is for `NONE`, so a check
    that only looks for `NONE` still hands out person ids.
    """
    task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
    ActionTaskContactFactory.create(task=task)
    plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.ALL_FOR_AUTHENTICATED
    plan.features.save()

    response = api_client.get(action_task_list_url)

    assert response.status_code == 200
    (payload,) = [t for t in response.json()['results'] if t['id'] == task.pk]
    assert payload['contact_persons'] == []


def test_rest_api_shows_task_contact_persons_to_an_authenticated_user(
    api_client, plan, action, action_task_list_url, plan_admin_user
):
    """The counterpart: someone who may see the authenticated site still gets them."""
    task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
    assignment = ActionTaskContactFactory.create(task=task)
    plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.ALL_FOR_AUTHENTICATED
    plan.features.save()
    api_client.force_login(plan_admin_user)

    response = api_client.get(action_task_list_url)

    assert response.status_code == 200
    (payload,) = [t for t in response.json()['results'] if t['id'] == task.pk]
    assert [cp['person'] for cp in payload['contact_persons']] == [assignment.person_id]


def test_rest_api_does_not_authorize_once_per_assignment(api_client, plan, action, action_task_list_url, user):
    """
    A public-site viewer must not cost one authorization query per contact person.

    `Person.visible_for_user()` depends only on the user and the plan, but it is asked per row, and under
    "authenticated only" it reaches `Person.is_public_site_viewer()`, which queries.
    """
    from actions.models.plan import PlanPublicSiteViewer

    viewer = PersonFactory.create(organization=plan.organization, user=user)
    PlanPublicSiteViewer.objects.create(plan=plan, person=viewer)
    plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.ALL_FOR_AUTHENTICATED
    plan.features.save()

    def count_queries_for(assignment_count: int) -> int:
        task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
        for _i in range(assignment_count):
            ActionTaskContactFactory.create(task=task)
        api_client.force_login(user)
        with CaptureQueriesContext(connection) as ctx:
            response = api_client.get(action_task_list_url)
        assert response.status_code == 200
        return len(ctx)

    few = count_queries_for(2)
    many = count_queries_for(6)

    assert many <= few, f'{many} queries with four more assignments than the {few} needed before'


def test_a_person_assigned_only_to_a_task_stays_available_to_the_plan(plan, action):
    """
    An external consultant may end up assigned to a task but to no action.

    `available_for_plan(include_contact_persons=True)` unions the action-level contact persons; without
    the task-level ones such a person drops out of the plan's people, which makes the admin reject their
    own unchanged assignment and the report export omit their name.
    """
    consultant = PersonFactory.create()
    assert consultant.organization not in plan.related_organizations.all()
    task = ActionTaskFactory.create(action=action)
    ActionTaskContactFactory.create(task=task, person=consultant)

    assert consultant in Person.objects.available_for_plan(plan, include_contact_persons=True)


def test_an_existing_task_assignment_still_validates_after_the_person_leaves_the_action(
    rf, action, plan_admin_user
):
    """Re-saving the action must not reject an assignment that is already stored."""
    consultant = PersonFactory.create()
    contact = ActionContactPerson.objects.create(action=action, person=consultant)
    task = ActionTaskFactory.create(action=action)
    assignment = ActionTaskContactFactory.create(task=task, person=consultant)
    contact.delete()  # the consultant is no longer a contact person of the action itself

    data = _base_post_data(action) | {
        'tasks-TOTAL_FORMS': '1',
        'tasks-INITIAL_FORMS': '1',
        'tasks-0-id': str(task.pk),
        'tasks-0-name': task.name,
        'tasks-0-due_at': task.due_at.isoformat(),
        'tasks-0-state': task.state,
        'tasks-0-responsible_parties-TOTAL_FORMS': '0',
        'tasks-0-responsible_parties-INITIAL_FORMS': '0',
        'tasks-0-contact_persons-TOTAL_FORMS': '1',
        'tasks-0-contact_persons-INITIAL_FORMS': '1',
        'tasks-0-contact_persons-0-id': str(assignment.pk),
        'tasks-0-contact_persons-0-person': str(consultant.pk),
    }

    form = _form_class(rf, plan_admin_user, action)(data=data, instance=action)

    assert form.is_valid(), form.formsets['tasks'].forms[0].formsets['contact_persons'].forms[0].errors


def test_an_organization_assigned_to_a_task_stays_a_valid_choice(rf, action, plan_admin_user):
    """
    An organization can leave the plan's hierarchy while a task is still assigned to it.

    As with the people above, the stored value must keep validating, or the action cannot be saved at
    all until the assignment is deleted.
    """
    organization = OrganizationFactory.create()
    action.plan.related_organizations.add(organization)
    task = ActionTaskFactory.create(action=action)
    assignment = ActionTaskResponsiblePartyFactory.create(task=task, organization=organization)
    action.plan.related_organizations.remove(organization)
    assert organization not in Organization.objects.available_for_plan(action.plan)

    data = _base_post_data(action) | {
        'tasks-TOTAL_FORMS': '1',
        'tasks-INITIAL_FORMS': '1',
        'tasks-0-id': str(task.pk),
        'tasks-0-name': task.name,
        'tasks-0-due_at': task.due_at.isoformat(),
        'tasks-0-state': task.state,
        'tasks-0-responsible_parties-TOTAL_FORMS': '1',
        'tasks-0-responsible_parties-INITIAL_FORMS': '1',
        'tasks-0-responsible_parties-0-id': str(assignment.pk),
        'tasks-0-responsible_parties-0-organization': str(organization.pk),
        'tasks-0-contact_persons-TOTAL_FORMS': '0',
        'tasks-0-contact_persons-INITIAL_FORMS': '0',
    }

    form = _form_class(rf, plan_admin_user, action)(data=data, instance=action)

    assert form.is_valid(), form.formsets['tasks'].forms[0].formsets['responsible_parties'].forms[0].errors


def test_rest_api_does_not_query_an_organization_per_redacted_contact(
    api_client, plan, action, action_task_list_url
):
    """
    At the `NAME` level the redacted copy carries the person's organization, which has to be prefetched.

    Otherwise the anonymous task list costs one organization query per assignment.
    """
    plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.NAME
    plan.features.save()

    def count_queries_for(assignment_count: int) -> int:
        task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
        for _i in range(assignment_count):
            ActionTaskContactFactory.create(task=task)
        with CaptureQueriesContext(connection) as ctx:
            response = api_client.get(action_task_list_url)
        assert response.status_code == 200
        return len(ctx)

    few = count_queries_for(2)
    many = count_queries_for(6)

    assert many <= few, f'{many} queries with four more assignments than the {few} needed before'


def test_a_departed_organization_cannot_be_assigned_to_another_task(rf, action, plan_admin_user):
    """
    Keeping a stored value valid must not make it valid everywhere.

    An organization that has left the plan stays acceptable on the assignment that already holds it,
    but posting it onto a different task is a cross-plan assignment and has to be rejected.
    """
    organization = OrganizationFactory.create()
    action.plan.related_organizations.add(organization)
    grandfathered_task = ActionTaskFactory.create(action=action)
    ActionTaskResponsiblePartyFactory.create(task=grandfathered_task, organization=organization)
    other_task = ActionTaskFactory.create(action=action)
    action.plan.related_organizations.remove(organization)

    data = _base_post_data(action) | {
        'tasks-TOTAL_FORMS': '1',
        'tasks-INITIAL_FORMS': '1',
        'tasks-0-id': str(other_task.pk),
        'tasks-0-name': other_task.name,
        'tasks-0-due_at': other_task.due_at.isoformat(),
        'tasks-0-state': other_task.state,
        'tasks-0-responsible_parties-TOTAL_FORMS': '1',
        'tasks-0-responsible_parties-INITIAL_FORMS': '0',
        'tasks-0-responsible_parties-0-organization': str(organization.pk),
        'tasks-0-contact_persons-TOTAL_FORMS': '0',
        'tasks-0-contact_persons-INITIAL_FORMS': '0',
    }

    form = _form_class(rf, plan_admin_user, action)(data=data, instance=action)

    assert not form.is_valid(), 'a departed organization must not be assignable to a new task'


def test_related_plan_actions_do_not_query_a_person_per_assignment(
    graphql_client_query_data, plan_factory, action_factory
):
    """
    `relatedPlanActions` returns other plans' actions, whose people also have to come from the cache.

    Each plan holds its own cache, so a resolver that reaches across plans has to fill all of them. The
    budget is the same one per task that `test_graphql_task_assignments_cost_at_most_one_query_per_task`
    pins; without the caches it was one more per assignment on top.
    """

    def related_plan_with_tasks(task_count: int):
        parent = plan_factory()
        child = plan_factory()
        parent.related_plans.add(child)
        action = action_factory(plan=child)
        for _i in range(task_count):
            task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
            ActionTaskContactFactory.create(task=task)
        return parent

    def count_queries_for(parent) -> int:
        query = """
            query($plan: ID!) {
              relatedPlanActions(plan: $plan) { tasks { contactPersons { person { firstName } } } }
            }
        """
        with CaptureQueriesContext(connection) as ctx:
            data = graphql_client_query_data(query, variables={'plan': parent.identifier})
        assert [t for a in data['relatedPlanActions'] for t in a['tasks']]
        return len(ctx)

    task_counts = (2, 6)
    small = count_queries_for(related_plan_with_tasks(task_counts[0]))
    large = count_queries_for(related_plan_with_tasks(task_counts[1]))

    extra_tasks = task_counts[1] - task_counts[0]
    assert large - small <= extra_tasks, (
        f'{large} queries for {task_counts[1]} tasks vs {small} for {task_counts[0]}: '
        'more than one query per task'
    )


def test_related_plan_actions_do_not_load_people_of_untouched_plans(
    graphql_client_query_data, plan_factory, action_factory
):
    """
    Filling a plan's people costs several queries, so it happens on first use.

    A regional deployment relates dozens of plans; a query that asks for nothing about people must not
    pay for any of them.
    """

    def parent_with_related_plans(count: int):
        parent = plan_factory()
        for _i in range(count):
            child = plan_factory()
            parent.related_plans.add(child)
            action_factory(plan=child)
        return parent

    def count_queries_for(parent) -> int:
        with CaptureQueriesContext(connection) as ctx:
            data = graphql_client_query_data(
                'query($plan: ID!) { relatedPlanActions(plan: $plan) { id } }',
                variables={'plan': parent.identifier},
            )
        assert data['relatedPlanActions']
        return len(ctx)

    few = count_queries_for(parent_with_related_plans(2))
    many = count_queries_for(parent_with_related_plans(6))

    assert many <= few, f'{many} queries for six related plans against {few} for two'
