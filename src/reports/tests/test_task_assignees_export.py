"""Task assignees must reach the spreadsheet and CSV report exports."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from typing import Any

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest

from actions.models.action import ActionTaskContactPerson, ActionTaskResponsibleParty
from actions.models.features import PlanFeatures
from actions.tests.factories import ActionTaskFactory
from orgs.tests.factories import OrganizationFactory
from people.tests.factories import PersonFactory
from reports.models import ActionSnapshot
from reports.report_formatters import ActionTasksFormatter
from reports.types import SerializedVersion
from reports.utils import group_by_model

from .fixtures import *

pytestmark = pytest.mark.django_db


def _format_tasks(report, action, user=None) -> str:
    """Run the tasks formatter over the action's snapshot the way the exporter does."""
    snapshot = ActionSnapshot.objects.get(action_version__object_id=str(action.pk))
    exporter = report.get_xlsx_exporter(user=user)
    related_objects = group_by_model([SerializedVersion.from_version_polymorphic(v) for v in snapshot.get_related_versions()])
    field = next(f for f in report.fields if f.block.name == 'tasks')
    formatter = ActionTasksFormatter(field.block)
    values = formatter.extract_action_values(
        exporter,
        field.value,
        snapshot.get_serialized_data().data,
        related_objects,
        {},
    )
    return values[0]


@pytest.fixture
def report_with_tasks(plan, report_type_factory, report_factory):
    return report_factory(type=report_type_factory(plan=plan, fields__0='tasks'))


def test_export_lists_task_assignees(plan, action, user, report_with_tasks):
    organization = OrganizationFactory.create(name='Department of Heat')
    plan.related_organizations.add(organization)
    person = PersonFactory.create(organization=plan.organization, first_name='Ada', last_name='Byron')
    task = ActionTaskFactory.create(action=action, name='Insulate the depot', due_at=datetime.date(2027, 1, 1))
    ActionTaskResponsibleParty.objects.create(task=task, organization=organization)
    ActionTaskContactPerson.objects.create(task=task, person=person)

    report_with_tasks.mark_as_complete(user)
    value = _format_tasks(report_with_tasks, action)

    assert 'Insulate the depot' in value
    assert 'Department of Heat' in value
    assert 'Ada Byron' in value


def test_export_of_a_task_without_assignees_is_unchanged(plan, action, user, report_with_tasks):
    """A task with no assignments must render exactly as before — no trailing separator."""
    ActionTaskFactory.create(action=action, name='Lonely task', due_at=datetime.date(2027, 1, 1))

    report_with_tasks.mark_as_complete(user)
    value = _format_tasks(report_with_tasks, action)

    assert value.startswith('• Lonely task [')
    assert '—' not in value


def test_export_skips_an_organization_that_left_the_plan(plan, action, user, report_with_tasks):
    """
    An assignee that is no longer available to the plan is skipped rather than crashing the export.

    This is also what an old snapshot looks like from the formatter's side: no resolvable assignment.
    """
    organization = OrganizationFactory.create(name='Department of Heat')
    plan.related_organizations.add(organization)
    task = ActionTaskFactory.create(action=action, name='Insulate the depot', due_at=datetime.date(2027, 1, 1))
    ActionTaskResponsibleParty.objects.create(task=task, organization=organization)
    report_with_tasks.mark_as_complete(user)
    assert 'Department of Heat' in _format_tasks(report_with_tasks, action), 'must be listed while still in the plan'

    plan.related_organizations.remove(organization)
    value = _format_tasks(report_with_tasks, action)

    assert 'Insulate the depot' in value
    assert 'Department of Heat' not in value


def test_a_snapshot_taken_before_the_assignment_existed_renders_without_it(plan, action, user, report_with_tasks):
    """
    Reports are point-in-time: assignments added after a snapshot must not appear in it.

    This is also what every pre-existing snapshot looks like, so it doubles as the backwards-compatibility
    check — the export must render them exactly as before rather than erroring on the missing versions.
    """
    organization = OrganizationFactory.create(name='Department of Heat')
    plan.related_organizations.add(organization)
    task = ActionTaskFactory.create(action=action, name='Insulate the depot', due_at=datetime.date(2027, 1, 1))
    report_with_tasks.mark_as_complete(user)

    ActionTaskResponsibleParty.objects.create(task=task, organization=organization)
    value = _format_tasks(report_with_tasks, action)

    assert value.startswith('• Insulate the depot [')
    assert 'Department of Heat' not in value


@pytest.mark.parametrize(
    'setting',
    [
        PlanFeatures.ContactPersonsPublicData.NONE,
        PlanFeatures.ContactPersonsPublicData.ALL_FOR_AUTHENTICATED,
    ],
)
def test_export_does_not_name_contact_persons_the_reader_may_not_see(
    plan, action, user, report_with_tasks, setting
):
    """
    A public plan's report can be downloaded anonymously, so the export follows the same rule as the APIs.

    Both of these settings make `PlanFeatures.public_contact_persons` false.
    """
    organization = OrganizationFactory.create(name='Department of Heat')
    plan.related_organizations.add(organization)
    person = PersonFactory.create(organization=plan.organization, first_name='Ada', last_name='Byron')
    task = ActionTaskFactory.create(action=action, name='Insulate the depot', due_at=datetime.date(2027, 1, 1))
    ActionTaskResponsibleParty.objects.create(task=task, organization=organization)
    ActionTaskContactPerson.objects.create(task=task, person=person)
    report_with_tasks.mark_as_complete(user)
    plan.features.contact_persons_public_data = setting
    plan.features.save()

    value = _format_tasks(report_with_tasks, action)

    assert 'Department of Heat' in value, 'organizations are not affected by the setting'
    assert 'Ada Byron' not in value


def test_export_hides_contact_persons_at_none_even_from_an_admin(plan, action, user, report_with_tasks, plan_admin_user):
    """
    "Do not show contact persons" keeps them out of published output for every reader.

    `Person.visible_for_user()` answers a looser question — an admin may see a contact person — and
    `Action.get_redacted_contact_persons()` makes that exception explicit for its own callers. An export
    is published output, so it follows the setting.
    """
    person = PersonFactory.create(organization=plan.organization, first_name='Ada', last_name='Byron')
    task = ActionTaskFactory.create(action=action, name='Insulate the depot', due_at=datetime.date(2027, 1, 1))
    ActionTaskContactPerson.objects.create(task=task, person=person)
    report_with_tasks.mark_as_complete(user)
    plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.NONE
    plan.features.save()

    value = _format_tasks(report_with_tasks, action, user=plan_admin_user)

    assert 'Ada Byron' not in value


def test_export_uses_the_setting_of_the_plan_that_owns_the_action(plan, plan_factory, report_with_tasks):
    """
    A report may include actions from child plans, each with its own contact-person setting.

    Checking the report's own plan would publish a child plan's people whenever the parent is permissive.
    """
    child = plan_factory()
    child.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.NONE
    child.features.save()
    plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.ALL
    plan.features.save()
    # Only the two attributes `_plan_of_action()` reads; building a real exporter would need a report
    # whose action list page includes related plans, which is beside the point here.
    exporter: Any = SimpleNamespace(plan=plan, child_plans=[child], user=None)

    assert ActionTasksFormatter._plan_of_action(exporter, {'plan_id': child.pk}) == child
    assert ActionTasksFormatter._plan_of_action(exporter, {'plan_id': plan.pk}) == plan
    assert ActionTasksFormatter._plan_of_action(exporter, {'plan_id': -1}) is None
    assert not child.contact_persons_published_to(None), "the child's own setting hides them"
    assert plan.contact_persons_published_to(None), "the parent's does not"


def test_export_names_contact_persons_for_a_reader_who_may_see_them(
    plan, action, user, report_with_tasks, plan_admin_user
):
    """The counterpart: an admin exporting the same plan still gets the names."""
    person = PersonFactory.create(organization=plan.organization, first_name='Ada', last_name='Byron')
    task = ActionTaskFactory.create(action=action, name='Insulate the depot', due_at=datetime.date(2027, 1, 1))
    ActionTaskContactPerson.objects.create(task=task, person=person)
    report_with_tasks.mark_as_complete(user)
    plan.features.contact_persons_public_data = PlanFeatures.ContactPersonsPublicData.ALL_FOR_AUTHENTICATED
    plan.features.save()

    value = _format_tasks(report_with_tasks, action, user=plan_admin_user)

    assert 'Ada Byron' in value


def test_export_names_a_person_assigned_only_to_a_task(plan, action, user, report_with_tasks, plan_admin_user):
    """
    The report's person lookup is the plan-available set, which has to include task-only assignees.

    Otherwise an external consultant's name silently disappears from the export the moment they stop
    being a contact person of the action.
    """
    consultant = PersonFactory.create(first_name='Xenia', last_name='Consultant')
    assert consultant.organization not in plan.related_organizations.all()
    task = ActionTaskFactory.create(action=action, name='Insulate the depot', due_at=datetime.date(2027, 1, 1))
    ActionTaskContactPerson.objects.create(task=task, person=consultant)

    report_with_tasks.mark_as_complete(user)
    value = _format_tasks(report_with_tasks, action, user=plan_admin_user)

    assert 'Xenia Consultant' in value


def test_marking_a_report_complete_does_not_query_per_task_assignment(
    plan_factory, action_factory, user, report_factory, report_type_factory
):
    """
    Following the assignment relations must not cost queries per task while snapshotting.

    reversion walks every followed relation of every task, and the report's own queries decide whether
    those walks hit the database or a prefetch.
    """
    def count_queries_for(task_count: int) -> int:
        plan = plan_factory()
        action = action_factory(plan=plan)
        for _i in range(task_count):
            task = ActionTaskFactory.create(action=action, due_at=datetime.date(2027, 1, 1))
            ActionTaskResponsibleParty.objects.create(task=task, organization=OrganizationFactory.create())
            ActionTaskContactPerson.objects.create(task=task, person=PersonFactory.create())
        report = report_factory(type=report_type_factory(plan=plan, fields__0='tasks'))
        with CaptureQueriesContext(connection) as ctx:
            report.mark_as_complete(user)
        return len(ctx)

    few = count_queries_for(2)
    many = count_queries_for(6)

    assert many <= few, f'{many} queries for six tasks against {few} for two'


def test_export_does_not_name_a_person_who_left_the_actions_plan(plan, plan_factory, report_with_tasks):
    """
    The report's people are a union over every plan it includes, so membership is checked per plan.

    A person still available in a sibling plan would otherwise be named for an action whose own plan
    they have left.
    """
    other_plan = plan_factory()
    outsider = PersonFactory.create(organization=other_plan.organization)
    exporter: Any = SimpleNamespace(
        plan=plan,
        child_plans=[other_plan],
        user=None,
        plan_current_related_objects=SimpleNamespace(
            persons={outsider.pk: outsider},
            persons_by_plan={plan.pk: {}, other_plan.pk: {outsider.pk: outsider}},
            organizations={},
            organizations_by_plan={plan.pk: {}, other_plan.pk: {}},
        ),
    )

    assert ActionTasksFormatter._persons_of_plan(exporter, plan) == {}
    assert ActionTasksFormatter._persons_of_plan(exporter, other_plan) == {outsider.pk: outsider}
