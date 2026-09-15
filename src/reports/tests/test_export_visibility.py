from __future__ import annotations

import pytest

from actions.tests.factories import ActionFactory

from .fixtures import *

pytestmark = pytest.mark.django_db


@pytest.fixture
def report(plan, report_type_factory, report_factory):
    """Build a minimal report for `plan`, still incomplete."""
    report_type = report_type_factory(plan=plan)
    report = report_factory(type=report_type)
    report.fields = report_type.fields
    report.save()
    return report


def exported_action_ids(report, **exporter_kwargs) -> set[int]:
    """Return the ids of the actions the exporter would write out."""
    exporter = report.get_xlsx_exporter(**exporter_kwargs)
    serialized_actions, _related = exporter._prepare_serialized_report_data()
    return {action.data['id'] for action in serialized_actions}


class TestActionIdsFilter:
    def test_incomplete_report_restricted_to_given_action_ids(self, report, plan):
        included = ActionFactory.create(plan=plan)
        ActionFactory.create(plan=plan)

        assert exported_action_ids(report, action_ids=[included.id]) == {included.id}

    def test_completed_report_restricted_to_given_action_ids(self, report, plan, user):
        included = ActionFactory.create(plan=plan)
        ActionFactory.create(plan=plan)
        report.mark_as_complete(user)

        assert exported_action_ids(report, action_ids=[included.id]) == {included.id}

    def test_completed_report_without_action_ids_includes_every_snapshot(self, report, plan, user):
        actions = [ActionFactory.create(plan=plan) for _ in range(2)]
        report.mark_as_complete(user)

        assert exported_action_ids(report) == {action.id for action in actions}
