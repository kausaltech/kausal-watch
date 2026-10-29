"""Before an admin marks a report complete, its confirmation shows what completing captures."""

from __future__ import annotations

import pytest

from actions.models import ActionResponsibleParty
from actions.tests.factories import (
    ActionContactFactory,
    ActionFactory,
    ActionResponsiblePartyFactory,
    WorkflowFactory,
)
from admin_site.tests.factories import ClientPlanFactory
from reports.tests.factories import ReportFactory, ReportTypeFactory

pytestmark = pytest.mark.django_db

COMPLETE_PATH = '/admin/plan_reports/report/mark_report_as_complete/{report}/'
UNDO_PATH = '/admin/plan_reports/report/undo_marking_report_as_complete/{report}/'


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def report(plan_with_pages):
    return ReportFactory.create(type=ReportTypeFactory.create(plan=plan_with_pages))


@pytest.fixture
def submitted_action(action, report, plan_admin_user):
    action.mark_as_complete_for_report(report, plan_admin_user)
    return action


@pytest.fixture
def unsubmitted_action(plan_with_pages):
    return ActionFactory.create(plan=plan_with_pages, name='Not yet submitted')


def _confirmation(admin_client, report) -> str:
    return admin_client.get(COMPLETE_PATH.format(report=report.pk)).content.decode()


def _moderate(plan) -> None:
    plan.features.moderation_workflow = WorkflowFactory.create()
    plan.features.save(update_fields=['moderation_workflow'])


def test_confirmation_explains_what_completing_does(admin_client, report, submitted_action):
    content = _confirmation(admin_client, report)
    assert 'freezes the data of its actions and indicators' in content
    assert 'It does not change the status of any action.' in content


def test_confirmation_warns_about_unsubmitted_actions(admin_client, report, submitted_action, unsubmitted_action):
    contact = ActionContactFactory.create(action=unsubmitted_action, primary_contact=True)
    party = ActionResponsiblePartyFactory.create(action=unsubmitted_action, role=ActionResponsibleParty.Role.PRIMARY)
    content = _confirmation(admin_client, report)
    assert '1 of 2 actions has not been submitted' in content
    assert 'They will be captured using their current values.' in content
    assert unsubmitted_action.name in content
    assert f'{contact.person} • {party.organization.name}' in content
    assert 'The submitted action will use its submitted values.' in content
    assert 'value="Submit actions and mark as complete"' in content


def test_confirmation_without_unsubmitted_actions_just_completes(admin_client, report, submitted_action):
    content = _confirmation(admin_client, report)
    assert 'not been submitted' not in content
    assert 'value="Mark as complete"' in content


def test_moderated_confirmation_captures_published_versions(admin_client, report, submitted_action, unsubmitted_action):
    _moderate(report.type.plan)
    content = _confirmation(admin_client, report)
    assert 'They will be captured using their current published versions.' in content


def test_moderated_confirmation_lists_submitted_actions_with_pending_changes(
    admin_client, plan_admin_user, report, submitted_action
):
    _moderate(report.type.plan)
    submitted_action.name = 'Changed after submitting'
    submitted_action.save_revision(user=plan_admin_user)
    content = _confirmation(admin_client, report)
    assert 'These submitted actions have changes waiting for approval.' in content
    assert 'report-actions-with-pending-changes' in content


def test_confirmation_without_moderation_lists_no_pending_changes(admin_client, report, submitted_action):
    assert 'changes waiting for approval' not in _confirmation(admin_client, report)


def test_undo_confirmation_names_the_submissions_completing_made(
    admin_client, plan_admin_user, report, submitted_action, unsubmitted_action
):
    report.mark_as_complete(plan_admin_user)
    content = admin_client.get(UNDO_PATH.format(report=report.pk)).content.decode()
    assert 'This also undoes the submissions that completing the report made for these actions:' in content
    assert unsubmitted_action.name in content
    assert 'value="Undo marking as complete"' in content
