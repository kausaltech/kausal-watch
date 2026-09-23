"""
Tests for the feature that governs the public site's sign-in link.

Signing in to the public site is possible for every plan; what varies is whether the link is
shown, which is all `allow_public_site_login` ever governed in the frontend. The field now says
so, and the pre-rename GraphQL name stays resolvable while the UI ships independently.
"""

from __future__ import annotations

import pytest

from actions.models import PlanFeatures

pytestmark = pytest.mark.django_db

FEATURES_QUERY = """
  query GetPlan($plan: ID!) {
    plan(id: $plan) {
      features {
        showLoginLinkInPublicUi
        allowPublicSiteLogin
      }
    }
  }
"""


def test_the_field_says_what_it_governs():
    field = PlanFeatures._meta.get_field('show_login_link_in_public_ui')
    assert field.default is True
    # Renamed in Django's model state only: the column keeps the name it was born with, so pods
    # running the previous release keep working through the deploy.
    assert field.db_column == 'allow_public_site_login'


@pytest.mark.parametrize('shown', [True, False])
def test_graphql_serves_the_value_under_both_names(graphql_client_query_data, plan_factory, shown):
    plan = plan_factory(visibility='public')
    plan.features.show_login_link_in_public_ui = shown
    plan.features.save()

    features = graphql_client_query_data(FEATURES_QUERY, variables={'plan': plan.identifier})['plan']['features']

    assert features['showLoginLinkInPublicUi'] is shown
    assert features['allowPublicSiteLogin'] is shown
