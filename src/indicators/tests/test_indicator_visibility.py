from __future__ import annotations

import json

import pytest

from aplans.utils import RestrictedVisibilityModel

from actions.tests.factories import ActionFactory, PlanFactory
from indicators.models.action_links import ActionIndicator
from indicators.models.indicator import Indicator, IndicatorLevel
from indicators.tests.factories import ActionIndicatorFactory, IndicatorFactory, IndicatorLevelFactory

pytestmark = pytest.mark.django_db

PLAN_INDICATORS_QUERY = """
query planIndicators($plan: ID!) {
  planIndicators(plan: $plan) {
    identifier
  }
}
"""


@pytest.fixture
def public_indicator(plan):
    indicator = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    return indicator


@pytest.fixture
def internal_indicator(plan):
    indicator = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    return indicator


def visible_identifiers(user) -> set[str | None]:
    qs = Indicator.objects.get_queryset().visible_for_user(user)
    return set(qs.values_list('identifier', flat=True))


class TestInternalIndicatorsAreForPlanStaffOnly:
    """
    Indicators marked as internal are shown only to the staff of a plan that uses them.

    Plan staff means anyone with admin access to that plan. Being merely authenticated is
    not enough, and staff of one plan gain no access to another plan's internal indicators.
    """

    def test_anonymous_user_sees_only_public_indicators(self, public_indicator, internal_indicator):
        assert visible_identifiers(None) == {public_indicator.identifier}

    def test_authenticated_user_without_a_role_sees_only_public_indicators(
        self, public_indicator, internal_indicator, user, person
    ):
        assert visible_identifiers(user) == {public_indicator.identifier}

    def test_plan_staff_see_internal_indicators_of_their_plan(self, public_indicator, internal_indicator, plan_admin_user):
        assert visible_identifiers(plan_admin_user) == {public_indicator.identifier, internal_indicator.identifier}

    def test_staff_of_one_plan_do_not_see_internal_indicators_of_another(self, plan_admin_user, public_indicator):
        other_plan = PlanFactory.create()
        other_internal = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)
        IndicatorLevelFactory.create(indicator=other_internal, plan=other_plan)

        assert other_internal.identifier not in visible_identifiers(plan_admin_user)

    def test_superuser_sees_internal_indicators(self, public_indicator, internal_indicator, superuser):
        assert visible_identifiers(superuser) == {public_indicator.identifier, internal_indicator.identifier}

    def test_superuser_sees_an_internal_indicator_with_no_plan(self, superuser):
        unconnected = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)

        assert unconnected.identifier in visible_identifiers(superuser)


class TestIndicatorIsVisibleForUser:
    """`Indicator.is_visible_for_user` must agree with the queryset filter."""

    def test_public_indicator_is_visible_to_anonymous_user(self, public_indicator):
        assert public_indicator.is_visible_for_user(None) is True

    def test_internal_indicator_is_hidden_from_anonymous_user(self, internal_indicator):
        assert internal_indicator.is_visible_for_user(None) is False

    def test_internal_indicator_is_hidden_from_authenticated_user_without_a_role(self, internal_indicator, user, person):
        assert internal_indicator.is_visible_for_user(user) is False

    def test_internal_indicator_is_visible_to_plan_staff(self, internal_indicator, plan_admin_user):
        assert internal_indicator.is_visible_for_user(plan_admin_user) is True

    def test_internal_indicator_is_visible_to_superuser(self, internal_indicator, superuser):
        assert internal_indicator.is_visible_for_user(superuser) is True


class TestRelatedQuerySetsFollowTheSameRule:
    def _action_indicator_ids(self, user) -> set[int]:
        qs = ActionIndicator.objects.get_queryset().visible_for_user(user)
        return set(qs.values_list('indicator_id', flat=True))

    def _indicator_level_ids(self, user) -> set[int]:
        qs = IndicatorLevel.objects.get_queryset().visible_for_user(user)
        return set(qs.values_list('indicator_id', flat=True))

    @pytest.fixture
    def action_links(self, plan, public_indicator, internal_indicator):
        action = ActionFactory.create(plan=plan)
        ActionIndicatorFactory.create(action=action, indicator=public_indicator)
        ActionIndicatorFactory.create(action=action, indicator=internal_indicator)
        return public_indicator, internal_indicator

    def test_action_links_hide_internal_indicators_from_anonymous_user(self, action_links):
        public, _internal = action_links

        assert self._action_indicator_ids(None) == {public.id}

    def test_action_links_hide_internal_indicators_from_authenticated_non_staff(self, action_links, user, person):
        public, _internal = action_links

        assert self._action_indicator_ids(user) == {public.id}

    def test_action_links_show_internal_indicators_to_plan_staff(self, action_links, plan_admin_user):
        public, internal = action_links

        assert self._action_indicator_ids(plan_admin_user) == {public.id, internal.id}

    def test_levels_hide_internal_indicators_from_authenticated_non_staff(
        self, public_indicator, internal_indicator, user, person
    ):
        assert self._indicator_level_ids(user) == {public_indicator.id}

    def test_levels_show_internal_indicators_to_plan_staff(self, public_indicator, internal_indicator, plan_admin_user):
        assert self._indicator_level_ids(plan_admin_user) == {public_indicator.id, internal_indicator.id}

    def test_levels_of_a_plan_hidden_from_the_user_are_excluded(self, plan_admin_user, public_indicator):
        """The plan constraint must apply to authenticated users too, not only anonymous ones."""
        hidden_plan = PlanFactory.create(published_at=None, features__expose_unpublished_plan_only_to_authenticated_user=True)
        elsewhere = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
        IndicatorLevelFactory.create(indicator=elsewhere, plan=hidden_plan)

        assert self._indicator_level_ids(plan_admin_user) == {public_indicator.id}


class TestPlanIndicatorsQueryVisibility:
    """The same rule must hold at the GraphQL endpoint."""

    def _query(self, graphql_client_query, plan) -> set[str]:
        response = graphql_client_query(PLAN_INDICATORS_QUERY, variables={'plan': plan.identifier})
        assert 'errors' not in response, json.dumps(response)
        return {indicator['identifier'] for indicator in response['data']['planIndicators']}

    def test_anonymous_user_sees_only_public_indicators(self, plan, public_indicator, internal_indicator, graphql_client_query):
        assert self._query(graphql_client_query, plan) == {public_indicator.identifier}

    def test_authenticated_user_without_a_role_sees_only_public_indicators(
        self, plan, public_indicator, internal_indicator, client, user, person, graphql_client_query
    ):
        client.force_login(user)

        assert self._query(graphql_client_query, plan) == {public_indicator.identifier}

    def test_plan_staff_see_internal_indicators(
        self, plan, public_indicator, internal_indicator, client, plan_admin_user, graphql_client_query
    ):
        client.force_login(plan_admin_user)

        assert self._query(graphql_client_query, plan) == {public_indicator.identifier, internal_indicator.identifier}
