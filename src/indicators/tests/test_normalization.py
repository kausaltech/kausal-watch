from __future__ import annotations

import json
import typing
from datetime import date

import pytest

from admin_site.tests.factories import ClientPlanFactory
from indicators.normalization import get_indicator_data_edit_url, get_normalization_warnings
from indicators.tests.factories import (
    CommonIndicatorNormalizatorFactory,
    DimensionCategoryFactory,
    IndicatorContactFactory,
    IndicatorFactory,
    IndicatorGoalFactory,
    IndicatorLevelFactory,
    IndicatorValueFactory,
)

if typing.TYPE_CHECKING:
    from django.test import Client

    from actions.models import Plan
    from indicators.models import Indicator
    from people.models import Person
    from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def population(plan: Plan) -> Indicator:
    indicator = IndicatorFactory.create(organization=plan.organization, name='Population')
    IndicatorValueFactory.create(indicator=indicator, date=date(2023, 12, 31), value=1000)
    IndicatorGoalFactory.create(indicator=indicator, date=date(2030, 12, 31), value=1100)
    return indicator


@pytest.fixture
def emissions(plan: Plan, population: Indicator) -> Indicator:
    """Return an indicator normalized by `population`, which lacks the population of 2024 and 2035."""
    indicator = IndicatorFactory.create(organization=plan.organization)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    assert indicator.common is not None
    assert population.common is not None
    CommonIndicatorNormalizatorFactory.create(normalizable=indicator.common, normalizer=population.common)
    IndicatorValueFactory.create(indicator=indicator, date=date(2023, 12, 31), value=50)
    IndicatorValueFactory.create(indicator=indicator, date=date(2024, 12, 31), value=40)
    IndicatorGoalFactory.create(indicator=indicator, date=date(2030, 12, 31), value=10)
    IndicatorGoalFactory.create(indicator=indicator, date=date(2035, 12, 31), value=5)
    indicator.handle_values_update()
    indicator.handle_goals_update()
    return indicator


class TestNormalizationGaps:
    def test_lists_values_and_goals_without_normalizer_data(self, emissions: Indicator, population: Indicator):
        [gap] = emissions.get_normalization_gaps()

        assert gap.normalizer == population.common
        assert gap.normalizer_indicator == population
        assert gap.value_dates == [date(2024, 12, 31)]
        assert gap.goal_dates == [date(2035, 12, 31)]

    def test_no_gap_once_normalizer_has_the_data(self, emissions: Indicator, population: Indicator):
        IndicatorValueFactory.create(indicator=population, date=date(2024, 12, 31), value=1010)
        IndicatorGoalFactory.create(indicator=population, date=date(2035, 12, 31), value=1200)
        # Updating the normalizer's data renormalizes the indicators it normalizes
        population.handle_values_update()
        population.handle_goals_update()

        assert emissions.get_normalization_gaps() == []

    def test_normalizer_value_of_zero_is_a_gap(self, emissions: Indicator, population: Indicator):
        IndicatorValueFactory.create(indicator=population, date=date(2024, 12, 31), value=0)
        population.handle_values_update()

        [gap] = emissions.get_normalization_gaps()
        assert gap.value_dates == [date(2024, 12, 31)]

    def test_organization_without_normalizer_indicator(self, emissions: Indicator, population: Indicator):
        population.delete()

        [gap] = emissions.get_normalization_gaps()
        assert gap.normalizer_indicator is None

    def test_categorized_values_are_a_gap(self, emissions: Indicator, population: Indicator):
        IndicatorValueFactory.create(indicator=population, date=date(2024, 12, 31), value=1010)
        population.handle_values_update()
        assert emissions.get_normalization_gaps()[0].has_unnormalized_categorized_values is False
        category = DimensionCategoryFactory.create()
        IndicatorValueFactory.create(indicator=emissions, date=date(2023, 12, 31), value=20, categories=[category])
        emissions.handle_values_update()

        [gap] = emissions.get_normalization_gaps()

        # The categorized value's date is not a missing population value
        assert gap.value_dates == []
        assert gap.has_unnormalized_categorized_values

    def test_indicator_without_data_has_no_gaps(self, plan: Plan, population: Indicator):
        indicator = IndicatorFactory.create(organization=plan.organization)
        assert indicator.common is not None
        assert population.common is not None
        CommonIndicatorNormalizatorFactory.create(normalizable=indicator.common, normalizer=population.common)

        assert indicator.get_normalization_gaps() == []

    def test_indicator_without_normalizers_has_no_gaps(self, population: Indicator):
        assert population.get_normalization_gaps() == []


class TestNormalizationWarnings:
    def test_names_the_dates_and_links_to_the_normalizer_data(
        self, emissions: Indicator, population: Indicator, plan: Plan, plan_admin_user: User
    ):
        [warning] = get_normalization_warnings(emissions, plan_admin_user, plan)

        assert '"Population"' in warning.message
        assert '2024, 2035 (goal)' in warning.message
        assert warning.normalizer_url == get_indicator_data_edit_url(population)

    def test_no_link_for_user_who_may_not_modify_the_normalizer(
        self, emissions: Indicator, plan: Plan, user: User, person: Person
    ):
        IndicatorContactFactory.create(indicator=emissions, person=person)

        [warning] = get_normalization_warnings(emissions, user, plan)

        assert '"Population"' in warning.message
        assert warning.normalizer_url is None
        assert warning.normalizer_link_text is None

    def test_categorized_values_get_their_own_warning(self, emissions: Indicator, plan: Plan, plan_admin_user: User):
        category = DimensionCategoryFactory.create()
        IndicatorValueFactory.create(indicator=emissions, date=date(2023, 12, 31), value=20, categories=[category])

        missing_data, categorized = get_normalization_warnings(emissions, plan_admin_user, plan)

        assert '2024, 2035 (goal)' in missing_data.message
        assert missing_data.normalizer_url is not None
        assert 'dimension categories' in categorized.message
        assert categorized.normalizer_url is None

    def test_missing_normalizer_indicator(self, emissions: Indicator, population: Indicator, plan: Plan, plan_admin_user: User):
        population.delete()

        [warning] = get_normalization_warnings(emissions, plan_admin_user, plan)

        assert 'has no indicator for it' in warning.message
        assert warning.normalizer_url is None


NORMALIZATION_WARNINGS_QUERY = """
query indicator($plan: ID!, $id: ID!, $restrictToPubliclyVisible: Boolean!) {
  indicator(plan: $plan, id: $id, restrictToPubliclyVisible: $restrictToPubliclyVisible) {
    normalizationWarnings {
      message
      normalizerUrl
      normalizerLinkText
    }
  }
}
"""


class TestNormalizationWarningsQuery:
    def _query(
        self, graphql_client_query, plan: Plan, indicator: Indicator, restrict_to_publicly_visible: bool = False
    ) -> list[dict[str, str | None]]:
        variables = {
            'plan': plan.identifier,
            'id': str(indicator.id),
            'restrictToPubliclyVisible': restrict_to_publicly_visible,
        }
        response = graphql_client_query(NORMALIZATION_WARNINGS_QUERY, variables=variables)
        assert 'errors' not in response, json.dumps(response)
        return response['data']['indicator']['normalizationWarnings']

    def test_plan_admin_gets_warnings(
        self,
        client: Client,
        plan: Plan,
        emissions: Indicator,
        population: Indicator,
        plan_admin_user: User,
        graphql_client_query,
    ):
        client.force_login(plan_admin_user)

        [warning] = self._query(graphql_client_query, plan, emissions)

        assert '2024' in typing.cast('str', warning['message'])
        assert warning['normalizerUrl'] == get_indicator_data_edit_url(population)
        assert warning['normalizerLinkText'] == 'Edit the data of "Population"'

    def test_anonymous_user_gets_no_warnings(self, plan: Plan, emissions: Indicator, graphql_client_query):
        assert self._query(graphql_client_query, plan, emissions, restrict_to_publicly_visible=True) == []

    @pytest.mark.usefixtures('person')
    def test_user_who_may_not_modify_the_indicator_gets_no_warnings(
        self, client: Client, plan: Plan, emissions: Indicator, user: User, graphql_client_query
    ):
        client.force_login(user)

        assert self._query(graphql_client_query, plan, emissions) == []


def test_edit_page_shows_warning(client: Client, plan: Plan, emissions: Indicator, plan_admin_user: User):
    ClientPlanFactory.create(plan=plan)
    client.force_login(plan_admin_user)

    response = client.get(f'/admin/indicators/indicator/edit/{emissions.pk}/')

    assert response.status_code == 200
    content = response.content.decode()
    assert '2024, 2035 (goal)' in content
    assert 'Edit the data of &quot;Population&quot;' in content
