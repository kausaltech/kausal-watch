from __future__ import annotations

import uuid

import pytest

from access_requests import mutations
from access_requests.models import AccessRequest
from access_requests.tests.factories import AccessRequestFactory
from actions.models import PlanPublicSiteViewer
from actions.tests.factories import PlanFactory
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db

WILDCARD_BASE = 'dummy.io'

MUTATION = """
  mutation RequestPlanAccess($hostname: String!, $input: RequestPlanAccessInput!)
  @context(input: { hostname: $hostname }) {
    requestPlanAccess(input: $input) {
      ok
    }
  }
"""


@pytest.fixture(autouse=True)
def isolated_rate_limit(monkeypatch):
    # The limiter counts per client IP in the shared cache; a group of its own keeps other tests' calls out.
    monkeypatch.setattr(mutations, 'RATE_LIMIT_GROUP', f'access-request-test-{uuid.uuid4()}')


@pytest.fixture
def plan(settings):
    settings.HOSTNAME_PLAN_DOMAINS = [WILDCARD_BASE]
    return PlanFactory.create(visibility='internal', features__enable_access_requests=True)


def _request(graphql_client_query, plan, **input_data):
    return graphql_client_query(
        MUTATION,
        variables={'hostname': f'{plan.identifier}.{WILDCARD_BASE}', 'input': input_data},
    )


def _error_code(response):
    assert 'errors' in response, response
    return response['errors'][0]['extensions']['code']


def test_anonymous_visitor_can_request_access_to_internal_plan(graphql_client_query, plan):
    response = _request(graphql_client_query, plan, email='Visitor@Example.com', firstName='Vera', lastName='Visitor')

    assert response == {'data': {'requestPlanAccess': {'ok': True}}}
    req = AccessRequest.objects.get()
    assert (req.plan, req.email, req.first_name, req.last_name) == (plan, 'visitor@example.com', 'Vera', 'Visitor')


def test_names_are_optional(graphql_client_query, plan):
    response = _request(graphql_client_query, plan, email='visitor@example.com')
    assert response['data']['requestPlanAccess']['ok'] is True
    assert AccessRequest.objects.get().first_name == ''


@pytest.mark.parametrize('situation', ['new', 'pending', 'rejected_before', 'has_access'])
def test_response_does_not_reveal_the_address_state(graphql_client_query, plan, situation):
    email = 'visitor@example.com'
    if situation == 'pending':
        AccessRequestFactory.create(plan=plan, email=email)
    elif situation == 'rejected_before':
        AccessRequestFactory.create(plan=plan, email=email, status=AccessRequest.Status.REJECTED)
    elif situation == 'has_access':
        PlanPublicSiteViewer.objects.create(plan=plan, person=PersonFactory.create(email=email))

    response = _request(graphql_client_query, plan, email=email)

    assert response == {'data': {'requestPlanAccess': {'ok': True}}}


def test_invalid_email_is_refused(graphql_client_query, plan):
    response = _request(graphql_client_query, plan, email='visitor@example')
    assert _error_code(response) == 'INVALID_EMAIL'
    assert not AccessRequest.objects.exists()


def test_refused_when_the_plan_does_not_take_requests(graphql_client_query, plan):
    plan.features.enable_access_requests = False
    plan.features.save()
    response = _request(graphql_client_query, plan, email='visitor@example.com')
    assert _error_code(response) == 'ACCESS_REQUESTS_DISABLED'
    assert not AccessRequest.objects.exists()


def test_refused_without_a_plan(graphql_client_query):
    response = graphql_client_query(
        'mutation($input: RequestPlanAccessInput!) { requestPlanAccess(input: $input) { ok } }',
        variables={'input': {'email': 'visitor@example.com'}},
    )
    assert _error_code(response) == 'PLAN_REQUIRED'


def test_rate_limited_per_client(graphql_client_query, plan, monkeypatch):
    monkeypatch.setattr(mutations, 'RATE_LIMIT', '2/m')
    for i in range(2):
        _request(graphql_client_query, plan, email=f'visitor{i}@example.com')
    response = _request(graphql_client_query, plan, email='one-too-many@example.com')
    assert _error_code(response) == 'RATE_LIMITED'
    assert AccessRequest.objects.count() == 2


def test_pending_requests_per_plan_are_capped(graphql_client_query, plan, monkeypatch):
    monkeypatch.setattr(mutations, 'MAX_PENDING_PER_PLAN', 2)
    AccessRequestFactory.create_batch(2, plan=plan)
    response = _request(graphql_client_query, plan, email='visitor@example.com')
    assert _error_code(response) == 'TOO_MANY_PENDING'
    assert AccessRequest.objects.count() == 2


def test_overlong_name_is_refused(graphql_client_query, plan):
    response = _request(graphql_client_query, plan, email='visitor@example.com', firstName='x' * 101)
    assert _error_code(response) == 'INVALID_NAME'
    assert not AccessRequest.objects.exists()
