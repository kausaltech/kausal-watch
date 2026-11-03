from __future__ import annotations

import json

from django.db import connection
from django.test.utils import CaptureQueriesContext

import pytest

from aplans.utils import RestrictedVisibilityModel

from actions.tests.factories import ActionFactory, PlanFactory
from indicators.models.action_links import ActionIndicator
from indicators.models.indicator import Indicator, IndicatorLevel
from indicators.tests.factories import ActionIndicatorFactory, IndicatorFactory, IndicatorLevelFactory
from orgs.tests.factories import OrganizationFactory

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
        hidden_plan = PlanFactory.create(published_at=None, visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)
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


RELATED_PLAN_INDICATORS_QUERY = """
query relatedPlanIndicators($plan: ID!, $first: Int) {
  relatedPlanIndicators(plan: $plan, first: $first) {
    identifier
  }
}
"""


class TestRelatedPlanIndicatorsQueryVisibility:
    """`relatedPlanIndicators` must follow the same rule as `planIndicators`."""

    @pytest.fixture
    def related_plan(self, plan):
        other_plan = PlanFactory.create()
        other_plan.related_plans.add(plan)
        return other_plan

    @pytest.fixture
    def related_indicators(self, related_plan):
        public = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
        internal = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)
        for indicator in (public, internal):
            IndicatorLevelFactory.create(indicator=indicator, plan=related_plan)
        return public, internal

    def _query(self, graphql_client_query, plan, **variables) -> set[str]:
        response = graphql_client_query(RELATED_PLAN_INDICATORS_QUERY, variables={'plan': plan.identifier, **variables})
        assert 'errors' not in response, json.dumps(response)
        return {indicator['identifier'] for indicator in response['data']['relatedPlanIndicators']}

    def test_anonymous_user_sees_only_public_indicators(self, plan, related_indicators, graphql_client_query):
        public, _internal = related_indicators

        assert self._query(graphql_client_query, plan) == {public.identifier}

    def test_authenticated_user_without_a_role_sees_only_public_indicators(
        self, plan, related_indicators, client, user, person, graphql_client_query
    ):
        public, _internal = related_indicators
        client.force_login(user)

        assert self._query(graphql_client_query, plan) == {public.identifier}

    def test_staff_of_the_queried_plan_do_not_see_another_plans_internal_indicators(
        self, plan, related_indicators, client, plan_admin_user, graphql_client_query
    ):
        public, _internal = related_indicators
        client.force_login(plan_admin_user)

        assert self._query(graphql_client_query, plan) == {public.identifier}

    def test_staff_of_the_related_plan_see_its_internal_indicators(
        self, plan, related_plan, related_indicators, client, person_factory, graphql_client_query
    ):
        public, internal = related_indicators
        staff = person_factory(general_admin_plans=[related_plan])
        client.force_login(staff.user)

        assert self._query(graphql_client_query, plan) == {public.identifier, internal.identifier}

    def test_first_limits_the_number_of_indicators(self, plan, related_plan, graphql_client_query):
        for _ in range(2):
            indicator = IndicatorFactory.create(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
            IndicatorLevelFactory.create(indicator=indicator, plan=related_plan)

        assert len(self._query(graphql_client_query, plan, first=1)) == 1


INDICATOR_LEVELS_QUERY = """
query planIndicators($plan: ID!) {
  planIndicators(plan: $plan) {
    identifier
    level(plan: $plan)
  }
}
"""


class TestVisibilityChecksDoNotScaleWithIndicatorCount:
    """
    Checking visibility must not cost a query per indicator.

    `Indicator.is_visible_for_user` is called once per node while resolving a list of
    indicators, so it has to answer from data the caller already fetched.
    """

    def _indicators(self, plan, count, visibility):
        for _ in range(count):
            indicator = IndicatorFactory.create(visibility=visibility)
            IndicatorLevelFactory.create(indicator=indicator, plan=plan)

    def test_is_visible_for_user_needs_no_query_when_plans_are_prefetched(self, plan, plan_admin_user, django_assert_num_queries):
        self._indicators(plan, 3, RestrictedVisibilityModel.VisibilityState.INTERNAL)
        indicators = list(Indicator.objects.get_queryset().visible_for_user(plan_admin_user).prefetch_related('plans'))
        assert len(indicators) == 3
        list(plan_admin_user.get_adminable_plans())  # The adminable plans are cached per user, not per indicator.

        with django_assert_num_queries(0):
            assert all(indicator.is_visible_for_user(plan_admin_user) for indicator in indicators)

    def _query_count(self, graphql_client_query, plan, count, visibility) -> int:
        self._indicators(plan, count, visibility)
        graphql_client_query(INDICATOR_LEVELS_QUERY, variables={'plan': plan.identifier})  # Warm the per-user caches.
        with CaptureQueriesContext(connection) as queries:
            response = graphql_client_query(INDICATOR_LEVELS_QUERY, variables={'plan': plan.identifier})
        assert 'errors' not in response, json.dumps(response)
        assert len(response['data']['planIndicators']) == count
        return len(queries.captured_queries)

    @pytest.mark.parametrize('visibility', list(RestrictedVisibilityModel.VisibilityState))
    def test_resolving_levels_costs_the_same_for_one_indicator_and_for_many(
        self, plan, client, plan_admin_user, graphql_client_query, visibility
    ):
        client.force_login(plan_admin_user)
        one = self._query_count(graphql_client_query, plan, 1, visibility)
        Indicator.objects.all().delete()
        many = self._query_count(graphql_client_query, plan, 5, visibility)

        assert many == one


INDICATOR_QUERY = """
query indicator($plan: ID!, $id: ID, $identifier: ID, $restrictToPubliclyVisible: Boolean!) {
  indicator(plan: $plan, id: $id, identifier: $identifier, restrictToPubliclyVisible: $restrictToPubliclyVisible) {
    id
  }
}
"""


class TestIndicatorQueryInAdmin:
    """
    The admin's indicator value editor resolves indicators that the plan may connect but hasn't.

    It passes `restrictToPubliclyVisible: false`. With that, the query matches the indicators
    the admin's indicator listing offers, while the public query stays limited to the plan.
    """

    def _query(self, graphql_client_query, plan, restrict_to_publicly_visible=False, **variables) -> str | None:
        response = graphql_client_query(
            INDICATOR_QUERY,
            variables={'plan': plan.identifier, 'restrictToPubliclyVisible': restrict_to_publicly_visible, **variables},
        )
        assert 'errors' not in response, json.dumps(response)
        indicator = response['data']['indicator']
        return indicator['id'] if indicator else None

    def _resolves(self, graphql_client_query, plan, indicator, restrict_to_publicly_visible=False) -> bool:
        resolved_id = self._query(graphql_client_query, plan, restrict_to_publicly_visible, id=str(indicator.id))
        return resolved_id is not None

    @pytest.fixture
    def unconnected_indicator(self, plan):
        related_org = OrganizationFactory.create()
        plan.related_organizations.add(related_org)
        return IndicatorFactory.create(organization=related_org)

    def test_general_admin_resolves_an_unconnected_indicator_of_a_related_organization(
        self, plan, unconnected_indicator, client, plan_admin_user, graphql_client_query
    ):
        client.force_login(plan_admin_user)

        assert self._resolves(graphql_client_query, plan, unconnected_indicator)

    def test_general_admin_resolves_an_indicator_of_the_plan(
        self, plan, internal_indicator, client, plan_admin_user, graphql_client_query
    ):
        client.force_login(plan_admin_user)

        assert self._resolves(graphql_client_query, plan, internal_indicator)

    def test_user_without_admin_access_does_not_resolve_an_unconnected_indicator(
        self, plan, unconnected_indicator, client, user, person, graphql_client_query
    ):
        client.force_login(user)

        assert not self._resolves(graphql_client_query, plan, unconnected_indicator)

    def test_contact_person_does_not_resolve_an_unconnected_indicator(
        self, plan, unconnected_indicator, client, action_contact_person_user, graphql_client_query
    ):
        """Admin access alone is not enough; connecting indicators is for general admins."""
        client.force_login(action_contact_person_user)

        assert not self._resolves(graphql_client_query, plan, unconnected_indicator)

    def test_public_query_does_not_resolve_an_unconnected_indicator(
        self, plan, unconnected_indicator, client, plan_admin_user, graphql_client_query
    ):
        client.force_login(plan_admin_user)

        assert not self._resolves(graphql_client_query, plan, unconnected_indicator, restrict_to_publicly_visible=True)

    def test_internal_indicator_of_another_plan_stays_hidden_from_general_admin(
        self, plan, client, plan_admin_user, graphql_client_query
    ):
        """
        The plan's organization owns the indicator, so the admin may connect it, but it is internal to another plan.

        Visibility still applies on top of what the admin may work with.
        """
        indicator = IndicatorFactory.create(
            organization=plan.organization, visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL
        )
        IndicatorLevelFactory.create(indicator=indicator, plan=PlanFactory.create())
        client.force_login(plan_admin_user)

        assert not self._resolves(graphql_client_query, plan, indicator)

    def test_superuser_resolves_an_indicator_of_the_plan_owned_by_an_unrelated_organization(
        self, plan, client, superuser, graphql_client_query
    ):
        indicator = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        client.force_login(superuser)

        assert self._resolves(graphql_client_query, plan, indicator)

    def test_lookup_by_identifier_stays_within_the_plan(self, plan, client, plan_admin_user, graphql_client_query):
        """Identifiers aren't unique, so an unconnected indicator with the same one must not make the lookup ambiguous."""
        connected = IndicatorFactory.create(organization=plan.organization, identifier='shared')
        IndicatorLevelFactory.create(indicator=connected, plan=plan)
        IndicatorFactory.create(organization=plan.organization, identifier='shared')
        client.force_login(plan_admin_user)

        assert self._query(graphql_client_query, plan, identifier='shared') == str(connected.id)
