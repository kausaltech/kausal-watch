from __future__ import annotations

import pytest

from content.models import SiteGeneralContent
from content.tests.factories import SiteGeneralContentFactory

pytestmark = pytest.mark.django_db

GENERAL_CONTENT_QUERY = """
    query($plan: ID!) {
      plan(id: $plan) {
        generalContent {
          id
          siteTitle
          siteDescription
          ownerUrl
          ownerName
          officialNameDescription
          copyrightText
          creativeCommonsLicense
          githubApiRepository
          githubUiRepository
          actionTerm
          actionTaskTerm
          organizationTerm
          indicatorTerm
          sitewideAnnouncement
        }
      }
    }
"""


def test_general_content_all_fields(graphql_client_query_data):
    sgc = SiteGeneralContentFactory.create(
        site_title='Test Plan',
        site_description='A test plan',
        owner_url='https://example.com',
        owner_name='Example City',
        official_name_description='Official description',
        copyright_text='Copyright 2026',
        creative_commons_license='CC BY 4.0',
        github_api_repository='https://github.com/example/api',
        github_ui_repository='https://github.com/example/ui',
    )
    data = graphql_client_query_data(GENERAL_CONTENT_QUERY, variables=dict(plan=sgc.plan.identifier))
    expected = {
        'plan': {
            'generalContent': {
                'id': str(sgc.pk),
                'siteTitle': sgc.site_title,
                'siteDescription': sgc.site_description,
                'ownerUrl': sgc.owner_url,
                'ownerName': sgc.owner_name,
                'officialNameDescription': sgc.official_name_description,
                'copyrightText': sgc.copyright_text,
                'creativeCommonsLicense': sgc.creative_commons_license,
                'githubApiRepository': sgc.github_api_repository,
                'githubUiRepository': sgc.github_ui_repository,
                'actionTerm': sgc.action_term.upper(),
                'actionTaskTerm': sgc.action_task_term.upper(),
                'organizationTerm': sgc.organization_term.upper(),
                'indicatorTerm': sgc.indicator_term.upper(),
                'sitewideAnnouncement': sgc.sitewide_announcement,
            },
        },
    }
    assert data == expected


@pytest.mark.parametrize('action_term', SiteGeneralContent.ActionTerm.values)
def test_action_term(graphql_client_query_data, action_term):
    sgc = SiteGeneralContentFactory.create(action_term=action_term)
    data = graphql_client_query_data(GENERAL_CONTENT_QUERY, variables=dict(plan=sgc.plan.identifier))
    assert data['plan']['generalContent']['actionTerm'] == action_term.upper()


@pytest.mark.parametrize('action_task_term', SiteGeneralContent.ActionTaskTerm.values)
def test_action_task_term(graphql_client_query_data, action_task_term):
    sgc = SiteGeneralContentFactory.create(action_task_term=action_task_term)
    data = graphql_client_query_data(GENERAL_CONTENT_QUERY, variables=dict(plan=sgc.plan.identifier))
    assert data['plan']['generalContent']['actionTaskTerm'] == action_task_term.upper()


@pytest.mark.parametrize('organization_term', SiteGeneralContent.OrganizationTerm.values)
def test_organization_term(graphql_client_query_data, organization_term):
    sgc = SiteGeneralContentFactory.create(organization_term=organization_term)
    data = graphql_client_query_data(GENERAL_CONTENT_QUERY, variables=dict(plan=sgc.plan.identifier))
    assert data['plan']['generalContent']['organizationTerm'] == organization_term.upper()


@pytest.mark.parametrize('indicator_term', SiteGeneralContent.IndicatorTerm.values)
def test_indicator_term(graphql_client_query_data, indicator_term):
    sgc = SiteGeneralContentFactory.create(indicator_term=indicator_term)
    data = graphql_client_query_data(GENERAL_CONTENT_QUERY, variables=dict(plan=sgc.plan.identifier))
    assert data['plan']['generalContent']['indicatorTerm'] == indicator_term.upper()
