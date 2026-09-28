"""
Tests for what a plan tells a visitor it is not yet showing.

A hostname whose availability is `SIGN_IN_REQUIRED` still has to render something: a page that
says which plan is behind the sign-in, dressed in that plan's theme. `PlanInterface` therefore
carries `name` and `themeIdentifier`, so both the plan's body and the restricted stand-in answer
them and the page needs no fragment per type.

This is a deliberate widening. A plan that is internal, or that has not launched, now gives its
name and theme to anyone who asks at its hostname — which is what the hostname is for.
"""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

import pytest

from actions.models.plan import PlanDomain

pytestmark = pytest.mark.django_db

IDENTITY_QUERY = """
  query GetPlansByHostname($hostname: String) {
    plansForHostname(hostname: $hostname) {
      __typename
      name
      identifier
      themeIdentifier
      domain { availability }
    }
  }
"""

TRANSLATED_IDENTITY_QUERY = """
  query GetPlansByHostname($hostname: String, $lang: String!) @locale(lang: $lang) {
    plansForHostname(hostname: $hostname) {
      __typename
      name
    }
  }
"""


def _sign_in_required_plan(plan_factory, plan_domain_factory, **kwargs):
    plan = plan_factory(
        visibility='internal',
        published_at=timezone.now() - timedelta(minutes=5),
        **kwargs,
    )
    domain = plan_domain_factory(plan=plan, deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION)
    return plan, domain


def test_a_restricted_plan_names_and_themes_itself(graphql_client_query_data, plan_factory, plan_domain_factory):
    """The sign-in page has nothing else to identify the plan by, or to style itself with."""
    plan, domain = _sign_in_required_plan(plan_factory, plan_domain_factory, theme_identifier='some-theme')

    plan_data = graphql_client_query_data(IDENTITY_QUERY, variables={'hostname': domain.hostname})['plansForHostname'][0]

    assert plan_data['domain']['availability'] == 'SIGN_IN_REQUIRED'
    assert plan_data['__typename'] == 'RestrictedPlanNode'
    assert plan_data['name'] == plan.name
    assert plan_data['identifier'] == plan.identifier
    assert plan_data['themeIdentifier'] == 'some-theme'


def test_a_restricted_plan_names_itself_in_its_own_language(
    graphql_client_query_data,
    plan_factory,
    plan_domain_factory,
):
    """
    The plan's own language is the only one this page can be sure of.

    A visitor here has not chosen a language and there is no site yet to have chosen one for
    them, and `plansForHostname` names no plan in a directive, so the query language falls back
    to the deployment's default — which would hand a Finnish plan's sign-in page an English name
    purely because the server is configured in English. `statusMessage` already answers in the
    plan's language for the same reason, and the name on the same page follows it.
    """
    plan, domain = _sign_in_required_plan(plan_factory, plan_domain_factory, primary_language='fi', other_languages=['en'])
    plan.name = 'Suomenkielinen nimi'
    plan.i18n = {'name_en': 'An English name'}
    plan.save()

    asked_in_english = graphql_client_query_data(TRANSLATED_IDENTITY_QUERY, variables={'hostname': domain.hostname, 'lang': 'en'})
    asked_without_a_language = graphql_client_query_data(IDENTITY_QUERY, variables={'hostname': domain.hostname})

    assert asked_in_english['plansForHostname'][0]['name'] == 'Suomenkielinen nimi'
    assert asked_without_a_language['plansForHostname'][0]['name'] == 'Suomenkielinen nimi'


def test_the_plan_body_still_answers_a_translated_name(
    graphql_client_query_data,
    plan_factory,
    plan_domain_factory,
):
    """The site itself is served in the visitor's language, and its name goes with it."""
    plan = plan_factory(
        visibility='public',
        published_at=timezone.now() - timedelta(minutes=5),
        primary_language='fi',
        other_languages=['en'],
    )
    plan.name = 'Suomenkielinen nimi'
    plan.i18n = {'name_en': 'An English name'}
    plan.save()
    domain = plan_domain_factory(plan=plan, deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION)

    data = graphql_client_query_data(TRANSLATED_IDENTITY_QUERY, variables={'hostname': domain.hostname, 'lang': 'en'})

    assert data['plansForHostname'][0]['__typename'] == 'Plan'
    assert data['plansForHostname'][0]['name'] == 'An English name'


def test_an_unavailable_plan_still_identifies_itself(graphql_client_query_data, plan_factory, plan_domain_factory):
    """
    A placeholder page is a page too.

    Nothing distinguishes the two dark states at the hostname, and a plan that has simply not
    launched yet is not a secret, so the identity is answered the same way in both.
    """
    plan = plan_factory(visibility='public', published_at=None)
    domain = plan_domain_factory(plan=plan, deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION)

    plan_data = graphql_client_query_data(IDENTITY_QUERY, variables={'hostname': domain.hostname})['plansForHostname'][0]

    assert plan_data['domain']['availability'] == 'UNAVAILABLE'
    assert plan_data['name'] == plan.name


def test_the_plan_body_still_answers_the_same_fields(graphql_client_query_data, plan_factory, plan_domain_factory):
    """Both implementations carry the interface's fields, so the page needs no fragment per type."""
    plan = plan_factory(visibility='public', published_at=timezone.now() - timedelta(minutes=5), theme_identifier='some-theme')
    domain = plan_domain_factory(plan=plan, deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION)

    plan_data = graphql_client_query_data(IDENTITY_QUERY, variables={'hostname': domain.hostname})['plansForHostname'][0]

    assert plan_data['__typename'] == 'Plan'
    assert plan_data['name'] == plan.name
    assert plan_data['themeIdentifier'] == 'some-theme'
