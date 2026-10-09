from __future__ import annotations

from unittest import mock

from graphql.error import GraphQLError

import pytest

from aplans.graphql_helpers import validate_client_url

from actions.tests.factories import ActionFactory, PlanFactory

pytestmark = pytest.mark.django_db

INVALID_CLIENT_URL_MESSAGE = 'clientUrl must be a valid URL'

PLAN_VIEW_URL_QUERY = """
query planViewUrl($plan: ID!, $clientUrl: String) {
  plan(id: $plan) {
    viewUrl(clientUrl: $clientUrl)
  }
}
"""

ACTION_VIEW_URL_QUERY = """
query actionViewUrl($plan: ID!, $identifier: ID!, $clientUrl: String) {
  action(plan: $plan, identifier: $identifier) {
    viewUrl(clientUrl: $clientUrl)
  }
}
"""


class TestValidateClientUrl:
    @pytest.mark.parametrize('client_url', [None, '', 'https://example.com', 'http://localhost:3000/fi'])
    def test_accepts_http_and_https_urls(self, client_url):
        validate_client_url(client_url)

    @pytest.mark.parametrize(
        'client_url', ['ftp://foo', 'example.com', 'javascript:alert(1)', 'http://[::1', 'https:foo', 'http://', 'https://:443']
    )
    def test_rejects_other_urls_with_graphql_error(self, client_url):
        with pytest.raises(GraphQLError, match=INVALID_CLIENT_URL_MESSAGE):
            validate_client_url(client_url)


class TestViewUrlInvalidClientUrl:
    """An invalid `clientUrl` is the client's mistake: a GraphQL error, not a server error for Sentry."""

    @pytest.fixture
    def plan(self, settings):
        settings.HOSTNAME_PLAN_DOMAINS = ['example.com']
        return PlanFactory.create(identifier='myplan')

    def test_plan_view_url_rejects_invalid_scheme(self, plan, graphql_client_query, contains_error):
        with mock.patch('sentry_sdk.capture_exception') as capture_exception:
            response = graphql_client_query(
                PLAN_VIEW_URL_QUERY,
                variables={'plan': plan.identifier, 'clientUrl': 'ftp://foo'},
            )
        assert contains_error(response, message=INVALID_CLIENT_URL_MESSAGE)
        capture_exception.assert_not_called()

    def test_action_view_url_rejects_invalid_scheme(self, plan, graphql_client_query, contains_error):
        action = ActionFactory.create(plan=plan)
        with mock.patch('sentry_sdk.capture_exception') as capture_exception:
            response = graphql_client_query(
                ACTION_VIEW_URL_QUERY,
                variables={'plan': plan.identifier, 'identifier': action.identifier, 'clientUrl': 'ftp://foo'},
            )
        assert contains_error(response, message=INVALID_CLIENT_URL_MESSAGE)
        capture_exception.assert_not_called()

    def test_plan_view_url_accepts_valid_client_url(self, plan, graphql_client_query_data):
        data = graphql_client_query_data(
            PLAN_VIEW_URL_QUERY,
            variables={'plan': plan.identifier, 'clientUrl': 'https://myplan.example.com'},
        )
        assert data['plan']['viewUrl'] == 'https://myplan.example.com'
