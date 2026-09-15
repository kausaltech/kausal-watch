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


@pytest.fixture
def indicator_report(plan, report_type_factory, report_factory):
    """Build a report whose single field is the related-indicators summary."""
    report_type = report_type_factory(plan=plan, fields__0='related_indicators')
    report = report_factory(type=report_type)
    report.fields = report_type.fields
    report.save()
    return report


class TestRelatedIndicatorsField:
    """
    The related-indicators column must describe only the indicators the requester may see.

    The column reports how many indicators an action has and whether any of them has a goal,
    so counting an indicator the requester cannot see discloses its existence.
    """

    @pytest.fixture
    def action_with_indicators(self, plan):
        from aplans.utils import RestrictedVisibilityModel

        from indicators.tests.factories import (
            ActionIndicatorFactory,
            IndicatorFactory,
            IndicatorGoalFactory,
            IndicatorLevelFactory,
        )

        action = ActionFactory.create(plan=plan)
        for visibility in (
            RestrictedVisibilityModel.VisibilityState.PUBLIC,
            RestrictedVisibilityModel.VisibilityState.INTERNAL,
        ):
            indicator = IndicatorFactory.create(organization=plan.organization, visibility=visibility)
            IndicatorLevelFactory.create(indicator=indicator, plan=plan)
            ActionIndicatorFactory.create(action=action, indicator=indicator)
            if visibility == RestrictedVisibilityModel.VisibilityState.INTERNAL:
                IndicatorGoalFactory.create(indicator=indicator)
        return action

    def _indicator_columns(self, report, user) -> list[str]:
        """Return the related-indicator cells of the single exported action row."""
        csv = report.get_xlsx_exporter(user=user).generate_csv()
        header, row = (line.split(',') for line in csv.strip().splitlines())
        return row[header.index('Indicators') :]

    def test_anonymous_viewer_does_not_see_internal_indicators(self, indicator_report, action_with_indicators):
        assert self._indicator_columns(indicator_report, None) == ['1', 'No']

    def test_authenticated_non_staff_does_not_see_internal_indicators(
        self, indicator_report, action_with_indicators, user, person
    ):
        assert self._indicator_columns(indicator_report, user) == ['1', 'No']

    def test_plan_staff_see_internal_indicators(self, indicator_report, action_with_indicators, plan_admin_user):
        assert self._indicator_columns(indicator_report, plan_admin_user) == ['2', 'Yes']

    def test_indicators_of_unrelated_organizations_are_not_counted(
        self, indicator_report, action_with_indicators, plan_admin_user
    ):
        from indicators.tests.factories import ActionIndicatorFactory, IndicatorFactory

        unrelated = IndicatorFactory.create()
        ActionIndicatorFactory.create(action=action_with_indicators, indicator=unrelated)

        assert self._indicator_columns(indicator_report, plan_admin_user) == ['2', 'Yes']


class TestLookupsAreScopedToTheReport:
    """
    The exporter must ask the database only about the rows the report actually contains.

    Otherwise a single export grows a query listing every action or indicator in the
    database, regardless of how few of them end up in the file.
    """

    def test_visible_indicators_are_looked_up_only_among_the_given_candidates(self, report, plan, plan_admin_user):
        from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory

        candidate = IndicatorFactory.create(organization=plan.organization)
        IndicatorLevelFactory.create(indicator=candidate, plan=plan)
        elsewhere = IndicatorFactory.create(organization=plan.organization)
        IndicatorLevelFactory.create(indicator=elsewhere, plan=plan)
        exporter = report.get_xlsx_exporter(user=plan_admin_user)

        assert exporter.visible_indicator_ids(frozenset({candidate.id})) == {candidate.id}
