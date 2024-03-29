import pytest

from actions.tests.factories import ActionFactory, ActionContactFactory, ActionResponsiblePartyFactory, PlanFactory
from orgs.tests.factories import OrganizationClassFactory, OrganizationFactory
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db


def test_person_node(graphql_client_query_data):
    person = PersonFactory()
    data = graphql_client_query_data(
        '''
        query($person: ID!) {
          person(id: $person) {
            __typename
            id
            firstName
            lastName
            title
            email
            organization {
              __typename
              id
            }
          }
        }
        ''',
        variables=dict(person=person.id)
    )
    expected = {
        'person': {
            '__typename': 'Person',
            'id': str(person.id),
            'firstName': person.first_name,
            'lastName': person.last_name,
            'title': person.title,
            'email': person.email,
            'organization': {
                '__typename': 'Organization',
                'id': str(person.organization.id),
            },
        }
    }
    assert data == expected


def test_organization_class_node(graphql_client_query_data):
    organization_class = OrganizationClassFactory()
    organization = OrganizationFactory(classification=organization_class)
    plan = PlanFactory(organization=organization)
    action = ActionFactory(plan=plan)
    ActionResponsiblePartyFactory(action=action, organization=plan.organization)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planOrganizations(plan: $plan) {
            classification {
              __typename
              id
              name
            }
          }
        }
        ''',
        variables=dict(plan=plan.identifier)
    )
    expected = {
        'planOrganizations': [{
            'classification': {
                '__typename': 'OrganizationClass',
                'id': str(organization_class.id),
                'name': organization_class.name,
            }
        }]
    }
    assert data == expected


def test_organization_node(graphql_client_query_data):
    organization = OrganizationFactory()
    plan = PlanFactory(organization=organization)
    action = ActionFactory(plan=plan)
    ActionResponsiblePartyFactory(action=action, organization=plan.organization)
    ActionContactFactory(action=action)
    # Implicitly create another plan not owned by `organization` for testing plansWithActionResponsibilities
    arp = ActionResponsiblePartyFactory(organization=organization)
    plan_with_action_responsiblity = arp.action.plan
    assert plan_with_action_responsiblity != plan
    assert plan_with_action_responsiblity.organization != organization
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planOrganizations(plan: $plan) {
            __typename
            id
            name
            description
            url
            # Tested in separate test case
            # ancestors {
            #   __typename
            #   id
            # }
            actionCount
            contactPersonCount
            plansWithActionResponsibilities {
              __typename
              id
            }
          }
        }
        ''',
        variables=dict(plan=plan.identifier)
    )
    expected = {
        'planOrganizations': [{
            '__typename': 'Organization',
            'id': str(organization.id),
            'name': organization.name,
            'description': str(organization.description),
            'url': organization.url,
            'actionCount': 1,
            'contactPersonCount': 1,
            'plansWithActionResponsibilities': [{
                '__typename': 'Plan',
                'id': str(plan.identifier),
            }, {
                '__typename': 'Plan',
                'id': str(plan_with_action_responsiblity.identifier),
            }],
        }]
    }
    assert data == expected


def test_organization_node_ancestors(graphql_client_query_data):
    superorganization = OrganizationFactory()
    organization = OrganizationFactory(parent=superorganization)
    OrganizationFactory(parent=organization)  # Add suborganization to check that it doesn't appear
    plan = PlanFactory(organization=organization)
    action = ActionFactory(plan=plan)
    ActionResponsiblePartyFactory(action=action, organization=plan.organization)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planOrganizations(plan: $plan) {
            __typename
            id
            ancestors {
              __typename
              id
            }
          }
        }
        ''',
        variables=dict(plan=plan.identifier)
    )
    expected = {
        'planOrganizations': [{
            '__typename': 'Organization',
            'id': str(organization.id),
            'ancestors': [{
                '__typename': 'Organization',
                'id': str(superorganization.id),
            }],
        }]
    }
    assert data == expected


def test_organization_node_ancestors_deep(graphql_client_query_data):
    supersuperorganization = OrganizationFactory()
    superorganization = OrganizationFactory(parent=supersuperorganization)
    organization = OrganizationFactory(parent=superorganization)
    plan = PlanFactory(organization=organization)
    action = ActionFactory(plan=plan)
    ActionResponsiblePartyFactory(action=action, organization=plan.organization)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planOrganizations(plan: $plan) {
            __typename
            id
            ancestors {
              __typename
              id
            }
          }
        }
        ''',
        variables=dict(plan=plan.identifier)
    )
    expected = {
        'planOrganizations': [{
            '__typename': 'Organization',
            'id': str(organization.id),
            'ancestors': [{
                '__typename': 'Organization',
                'id': str(supersuperorganization.id),
            }, {
                '__typename': 'Organization',
                'id': str(superorganization.id),
            }],
        }]
    }
    assert data == expected


"""
FIXME: Re-enable

def test_site_general_content_node(graphql_client_query_data):
    site_general_content = SiteGeneralContentFactory()
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            generalContent {
              __typename
              id
              siteTitle
              siteDescription
              heroContent
              ownerUrl
              ownerName
              actionShortDescription
              indicatorShortDescription
              actionListLeadContent
              indicatorListLeadContent
              dashboardLeadContent
              officialNameDescription
              copyrightText
              creativeCommonsLicense
              githubApiRepository
              githubUiRepository
            }
          }
        }
        ''',
        variables=dict(plan=site_general_content.plan.identifier)
    )
    expected = {
        'plan': {
            'generalContent': {
                '__typename': 'SiteGeneralContent',
                'id': str(site_general_content.id),
                'siteTitle': site_general_content.site_title,
                'siteDescription': site_general_content.site_description,
                'heroContent': site_general_content.hero_content,
                'ownerUrl': site_general_content.owner_url,
                'ownerName': site_general_content.owner_name,
                'actionShortDescription': site_general_content.action_short_description,
                'indicatorShortDescription': site_general_content.indicator_short_description,
                'actionListLeadContent': site_general_content.action_list_lead_content,
                'indicatorListLeadContent': site_general_content.indicator_list_lead_content,
                'dashboardLeadContent': site_general_content.dashboard_lead_content,
                'officialNameDescription': site_general_content.official_name_description,
                'copyrightText': site_general_content.copyright_text,
                'creativeCommonsLicense': site_general_content.creative_commons_license,
                'githubApiRepository': site_general_content.github_api_repository,
                'githubUiRepository': site_general_content.github_ui_repository,
            }
        }
    }
    assert data == expected
"""
