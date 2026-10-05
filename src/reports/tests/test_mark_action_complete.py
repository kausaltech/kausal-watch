"""An action can only be marked complete, or have that undone, for an open report of its own plan."""

from __future__ import annotations

import pytest

from actions.tests.factories import ActionFactory, PlanFactory
from reports.tests.factories import ReportFactory, ReportTypeFactory
from reports.views import MarkActionAsCompleteView

from .fixtures import *

pytestmark = pytest.mark.django_db


@pytest.fixture
def report(plan):
    return ReportFactory.create(type=ReportTypeFactory.create(plan=plan))


@pytest.fixture
def other_plan_report():
    return ReportFactory.create(type=ReportTypeFactory.create(plan=PlanFactory.create()))


def _view(action, report) -> MarkActionAsCompleteView:
    view = MarkActionAsCompleteView.__new__(MarkActionAsCompleteView)
    view.action = action
    view.report = report
    return view


def test_cannot_mark_action_complete_for_report_of_another_plan(action, superuser, other_plan_report):
    with pytest.raises(ValueError, match='does not belong'):
        action.mark_as_complete_for_report(other_plan_report, superuser)
    assert not other_plan_report.action_snapshots.exists()


def test_cannot_undo_for_report_of_another_plan(action, superuser, other_plan_report):
    with pytest.raises(ValueError, match='does not belong'):
        action.undo_marking_as_complete_for_report(other_plan_report, superuser)


def test_cannot_mark_action_complete_for_completed_report(plan, superuser, report):
    report.mark_as_complete(superuser)
    new_action = ActionFactory.create(plan=plan)

    with pytest.raises(ValueError, match=r'The report .* is already marked as complete'):
        new_action.mark_as_complete_for_report(report, superuser)
    assert not new_action.is_complete_for_report(report)


def test_cannot_undo_for_completed_report(action, superuser, report):
    action.mark_as_complete_for_report(report, superuser)
    report.mark_as_complete(superuser)

    with pytest.raises(ValueError, match=r'The report .* is already marked as complete'):
        action.undo_marking_as_complete_for_report(report, superuser)
    assert action.is_complete_for_report(report)


def test_view_permits_action_editor_for_report_of_the_action_plan(action, action_contact_person_user, report):
    assert _view(action, report).check_action_permitted(action_contact_person_user)


def test_view_rejects_report_of_another_plan(action, superuser, other_plan_report):
    assert not _view(action, other_plan_report).check_action_permitted(superuser)


def test_view_enforces_admin_only_completion(action, action_contact_person_user, plan_admin_user, report):
    report.type.only_plan_admins_can_mark_actions_as_complete = True
    report.type.save()

    assert not _view(action, report).check_action_permitted(action_contact_person_user)
    assert _view(action, report).check_action_permitted(plan_admin_user)
