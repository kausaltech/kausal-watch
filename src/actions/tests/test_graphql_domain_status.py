"""
Tests for the per-hostname signal the public UI gates on.

`PlanDomain.status` names the page the frontend should render for this viewer at this hostname:
`AVAILABLE` (the site), `SIGN_IN_REQUIRED` (a sign-in page) or `UNAVAILABLE` (a placeholder with
no way in). It folds together the plan's visibility, the viewer's access, whether the production
surface has launched, and whether the hostname is a production or a preview surface.

`__typename` follows the same answer — `Plan` exactly when the status is `AVAILABLE` — so the two
can never disagree. Them disagreeing is what let a production domain serve a plan nobody had
published while reporting itself unpublished.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

import pytest

from kausal_common.testing.utils import parse_table

from actions.models.plan import PlanDomain, PublicationStatus

pytestmark = pytest.mark.django_db

STATUS_QUERY = """
  query GetPlansByHostname($hostname: String) {
    plansForHostname(hostname: $hostname) {
      __typename
      loginEnabled
      domain { status statusMessage }
    }
  }
"""

WILDCARD_BASE = 'dummy.io'

# surface:    production  — an explicit PlanDomain row, the customer's real hostname
#             preview     — an explicit row tagged as a preview deployment
#             wildcard    — no row at all; the hostname is synthesised from the plan identifier
# user:       anonymous / with_access (a general admin of this plan) /
#             without_access (signed in, but a general admin of another plan only)
SURFACE_MATRIX = """
    surface     visibility  launched  user            status            typename
    production  public      +         anonymous       AVAILABLE         Plan
    production  public      -         anonymous       UNAVAILABLE       RestrictedPlanNode
    production  public      -         with_access     UNAVAILABLE       RestrictedPlanNode
    production  internal    +         anonymous       SIGN_IN_REQUIRED  RestrictedPlanNode
    production  internal    +         with_access     AVAILABLE         Plan
    production  internal    +         without_access  UNAVAILABLE       RestrictedPlanNode
    production  internal    -         anonymous       UNAVAILABLE       RestrictedPlanNode
    production  internal    -         with_access     UNAVAILABLE       RestrictedPlanNode
    preview     public      -         anonymous       AVAILABLE         Plan
    preview     internal    -         anonymous       SIGN_IN_REQUIRED  RestrictedPlanNode
    preview     internal    -         with_access     AVAILABLE         Plan
    preview     internal    -         without_access  UNAVAILABLE       RestrictedPlanNode
    wildcard    public      -         anonymous       AVAILABLE         Plan
    wildcard    public      +         anonymous       AVAILABLE         Plan
    wildcard    internal    -         anonymous       SIGN_IN_REQUIRED  RestrictedPlanNode
    wildcard    internal    -         with_access     AVAILABLE         Plan
    wildcard    internal    -         without_access  UNAVAILABLE       RestrictedPlanNode
"""


def _setup(surface, visibility, launched, user, plan_factory, plan_domain_factory, person_factory, client, settings):
    plan = plan_factory(
        visibility=visibility,
        published_at=timezone.now() - timedelta(minutes=5) if launched else None,
    )
    if surface == 'wildcard':
        settings.HOSTNAME_PLAN_DOMAINS = [WILDCARD_BASE]
        hostname = f'{plan.identifier}.{WILDCARD_BASE}'
    else:
        environment = (
            PlanDomain.DeploymentEnvironment.PRODUCTION if surface == 'production' else PlanDomain.DeploymentEnvironment.PREVIEW
        )
        hostname = plan_domain_factory(plan=plan, deployment_environment=environment).hostname

    if user == 'with_access':
        client.force_login(person_factory(general_admin_plans=[plan]).user)
    elif user == 'without_access':
        client.force_login(person_factory(general_admin_plans=[plan_factory()]).user)
    return hostname


@pytest.mark.parametrize(*parse_table(SURFACE_MATRIX))
def test_domain_status_names_the_page_to_render(
    graphql_client_query_data,
    plan_factory,
    plan_domain_factory,
    person_factory,
    client,
    settings,
    surface,
    visibility,
    launched,
    user,
    status,
    typename,
):
    hostname = _setup(
        surface,
        visibility,
        launched,
        user,
        plan_factory,
        plan_domain_factory,
        person_factory,
        client,
        settings,
    )
    data = graphql_client_query_data(STATUS_QUERY, variables={'hostname': hostname})
    assert data['plansForHostname'][0]['domain']['status'] == status


@pytest.mark.parametrize(*parse_table(SURFACE_MATRIX))
def test_plan_type_agrees_with_domain_status(
    graphql_client_query_data,
    plan_factory,
    plan_domain_factory,
    person_factory,
    client,
    settings,
    surface,
    visibility,
    launched,
    user,
    status,
    typename,
):
    hostname = _setup(
        surface,
        visibility,
        launched,
        user,
        plan_factory,
        plan_domain_factory,
        person_factory,
        client,
        settings,
    )
    data = graphql_client_query_data(STATUS_QUERY, variables={'hostname': hostname})
    assert data['plansForHostname'][0]['__typename'] == typename


def test_unlaunched_production_domain_hides_a_public_plan(graphql_client_query_data, plan_factory, plan_domain_factory):
    """
    Regression test for the exposure this work started from.

    A plan whose data is public but whose production domain has not launched must not be served
    there. Before, the domain reported itself unpublished while the plan resolved as fully
    readable, and the frontend followed the plan.
    """
    plan = plan_factory(visibility='public', published_at=None)
    domain = plan_domain_factory(plan=plan, deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION)

    plan_data = graphql_client_query_data(STATUS_QUERY, variables={'hostname': domain.hostname})['plansForHostname'][0]

    assert plan_data['domain']['status'] == 'UNAVAILABLE'
    assert plan_data['__typename'] == 'RestrictedPlanNode'
    assert plan_data['loginEnabled'] is False


def test_login_is_offered_only_where_signing_in_leads_somewhere(
    graphql_client_query_data,
    plan_factory,
    plan_domain_factory,
):
    """A hostname serving nothing must not offer a sign-in button that cannot reveal anything."""
    launched = timezone.now() - timedelta(minutes=5)
    unavailable = plan_domain_factory(plan=plan_factory(visibility='public', published_at=None))
    sign_in = plan_domain_factory(plan=plan_factory(visibility='internal', published_at=launched))

    def login_enabled(hostname):
        data = graphql_client_query_data(STATUS_QUERY, variables={'hostname': hostname})
        return data['plansForHostname'][0]['loginEnabled']

    assert login_enabled(unavailable.hostname) is False
    assert login_enabled(sign_in.hostname) is True


def test_a_signed_in_viewer_without_access_is_not_asked_to_sign_in_again(
    graphql_client_query_data,
    plan_factory,
    plan_domain_factory,
    person_factory,
    client,
):
    """
    Signing in has already happened, and it did not reveal the plan.

    Asking again cannot change the answer, and the frontend treats an authenticated session on
    the sign-in page as a sign-in that has just completed, so it would navigate back to the same
    page over and over.
    """
    launched = timezone.now() - timedelta(minutes=5)
    domain = plan_domain_factory(plan=plan_factory(visibility='internal', published_at=launched))
    client.force_login(person_factory(general_admin_plans=[plan_factory()]).user)

    plan_data = graphql_client_query_data(STATUS_QUERY, variables={'hostname': domain.hostname})['plansForHostname'][0]

    assert plan_data['domain']['status'] == 'UNAVAILABLE'
    assert plan_data['loginEnabled'] is False


STATUS_MESSAGE_QUERY = """
  query GetPlansByHostname($hostname: String) {
    plansForHostname(hostname: $hostname) {
      loginEnabled
      statusMessage
      domain { status statusMessage }
    }
  }
"""


@pytest.mark.parametrize(*parse_table(SURFACE_MATRIX))
def test_status_message_is_sent_only_where_sign_in_is_required(
    graphql_client_query_data,
    plan_factory,
    plan_domain_factory,
    person_factory,
    client,
    settings,
    surface,
    visibility,
    launched,
    user,
    status,
    typename,
):
    """
    A message accompanies the sign-in page, and nothing else.

    The UI released before this model forwards `loginEnabled` to its placeholder only alongside a
    non-empty message, so without one it would hide the sign-in button from viewers who need it.
    Remove once no deployed UI predates `domain.status`.
    """
    hostname = _setup(
        surface,
        visibility,
        launched,
        user,
        plan_factory,
        plan_domain_factory,
        person_factory,
        client,
        settings,
    )
    plan_data = graphql_client_query_data(STATUS_MESSAGE_QUERY, variables={'hostname': hostname})['plansForHostname'][0]

    sign_in_required = status == 'SIGN_IN_REQUIRED'
    assert bool(plan_data['domain']['statusMessage']) is sign_in_required
    assert plan_data['statusMessage'] == plan_data['domain']['statusMessage']
    assert plan_data['loginEnabled'] is sign_in_required


def test_status_message_is_in_the_plan_language(graphql_client_query_data, plan_factory, plan_domain_factory):
    domain = plan_domain_factory(plan=plan_factory(visibility='internal', primary_language='fi'))
    data = graphql_client_query_data(STATUS_MESSAGE_QUERY, variables={'hostname': domain.hostname})
    assert data['plansForHostname'][0]['domain']['statusMessage'] == 'Sivusto ei ole julkinen tällä hetkellä.'


@pytest.mark.parametrize(
    ('override', 'expected_status'),
    [
        (PublicationStatus.PUBLISHED, 'AVAILABLE'),
        (PublicationStatus.UNPUBLISHED, 'UNAVAILABLE'),
    ],
)
def test_publication_status_override_forces_the_launch_state_of_one_hostname(
    graphql_client_query_data,
    plan_factory,
    plan_domain_factory,
    override,
    expected_status,
):
    """The per-domain override still forces whether a hostname is switched on, never who may read."""
    plan = plan_factory(
        visibility='public',
        published_at=None if override == PublicationStatus.PUBLISHED else timezone.now() - timedelta(minutes=5),
    )
    domain = plan_domain_factory(plan=plan, publication_status_override=override)
    data = graphql_client_query_data(STATUS_QUERY, variables={'hostname': domain.hostname})
    assert data['plansForHostname'][0]['domain']['status'] == expected_status
