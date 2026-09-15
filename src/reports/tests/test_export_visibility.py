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


@pytest.fixture
def hidden_plan(plan, plan_features):
    """Make `plan` unpublished and reachable only by authenticated users who may view it."""
    plan.published_at = None
    plan.save()
    plan.features.expose_unpublished_plan_only_to_authenticated_user = True
    plan.features.save()
    return plan


class TestVisibilityFilter:
    """
    The exporter must show each requester only the actions they are allowed to see.

    `ActionQuerySet.visible_for_user` restricts to plans visible to the user, and shows
    internal actions only to the staff of their own plan. Both the live and the completed
    branch of the exporter must apply it identically.
    """

    def _public_and_internal_actions(self, plan):
        from aplans.utils import RestrictedVisibilityModel

        public = ActionFactory.create(plan=plan, visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
        internal = ActionFactory.create(plan=plan, visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)
        return public, internal

    def test_incomplete_report_hides_internal_actions_from_anonymous_viewer(self, report, plan):
        public, _internal = self._public_and_internal_actions(plan)

        assert exported_action_ids(report, user=None) == {public.id}

    def test_completed_report_hides_internal_actions_from_anonymous_viewer(self, report, plan, user):
        public, _internal = self._public_and_internal_actions(plan)
        report.mark_as_complete(user)

        assert exported_action_ids(report, user=None) == {public.id}

    def test_incomplete_report_hides_internal_actions_from_authenticated_non_staff(self, report, plan, user, person):
        public, _internal = self._public_and_internal_actions(plan)

        assert exported_action_ids(report, user=user) == {public.id}

    def test_completed_report_hides_internal_actions_from_authenticated_non_staff(self, report, plan, user, person):
        public, _internal = self._public_and_internal_actions(plan)
        report.mark_as_complete(user)

        assert exported_action_ids(report, user=user) == {public.id}

    def test_incomplete_report_shows_internal_actions_to_plan_staff(self, report, plan, plan_admin_user):
        public, internal = self._public_and_internal_actions(plan)

        assert exported_action_ids(report, user=plan_admin_user) == {public.id, internal.id}

    def test_completed_report_shows_internal_actions_to_plan_staff(self, report, plan, plan_admin_user):
        public, internal = self._public_and_internal_actions(plan)
        report.mark_as_complete(plan_admin_user)

        assert exported_action_ids(report, user=plan_admin_user) == {public.id, internal.id}

    def test_incomplete_report_of_hidden_plan_is_empty_for_anonymous_viewer(self, report, hidden_plan):
        self._public_and_internal_actions(hidden_plan)

        assert exported_action_ids(report, user=None) == set()

    def test_completed_report_of_hidden_plan_is_empty_for_anonymous_viewer(self, report, hidden_plan, user):
        self._public_and_internal_actions(hidden_plan)
        report.mark_as_complete(user)

        assert exported_action_ids(report, user=None) == set()

    def test_completed_report_of_hidden_plan_is_exported_for_permitted_user(self, report, hidden_plan, user_factory):
        public, internal = self._public_and_internal_actions(hidden_plan)
        superuser = user_factory(is_superuser=True)
        report.mark_as_complete(superuser)

        assert exported_action_ids(report, user=superuser) == {public.id, internal.id}

    def test_completed_report_action_ids_and_visibility_filters_combine(self, report, plan, user):
        public, internal = self._public_and_internal_actions(plan)
        report.mark_as_complete(user)

        assert exported_action_ids(report, action_ids=[public.id, internal.id], user=None) == {public.id}
