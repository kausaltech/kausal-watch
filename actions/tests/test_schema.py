import pytest

from actions.models import get_default_language, CategoryTypeMetadata
from actions.tests.factories import (
    CategoryFactory, CategoryMetadataChoiceFactory, CategoryTypeFactory, CategoryTypeMetadataFactory,
    CategoryTypeMetadataChoiceFactory, PlanFactory, PlanWithRelatedObjectsFactory
)
from admin_site.tests.factories import AdminHostnameFactory, ClientPlanFactory


@pytest.mark.django_db
def test_plan_domain_node(graphql_client_query_data):
    plan = PlanFactory()
    domain = plan.domains.first()
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $hostname: String!) {
          plan(id: $plan) {
            domain(hostname: $hostname) {
              id
              hostname
              googleSiteVerificationTag
              matomoAnalyticsUrl
            }
          }
        }
        ''',
        variables=dict(plan=plan.identifier, hostname=domain.hostname)
    )
    expected = {
        'plan': {
            'domain': {
                'id': str(domain.id),
                'hostname': domain.hostname,
                'googleSiteVerificationTag': domain.google_site_verification_tag,
                'matomoAnalyticsUrl': domain.matomo_analytics_url,
            },
        }
    }
    assert data == expected


@pytest.mark.django_db
def test_category_metadata_choice_node(graphql_client_query_data):
    plan = PlanFactory()
    ct = CategoryTypeFactory(plan=plan)
    ctm = CategoryTypeMetadataFactory(type=ct, format=CategoryTypeMetadata.MetadataFormat.ORDERED_CHOICE)
    ctmc = CategoryTypeMetadataChoiceFactory(metadata=ctm)
    # Create a category with metadata so we can access the CategoryMetadataChoiceNode via planCategories
    category = CategoryFactory(type=ct)
    CategoryMetadataChoiceFactory(metadata=ctm, category=category, choice=ctmc)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            metadata {
              ... on CategoryMetadataChoice {
                key
                keyIdentifier
                value
                valueIdentifier
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'metadata': [{
                'key': ctm.name,
                'keyIdentifier': ctm.identifier,
                'value': ctmc.name,
                'valueIdentifier': ctmc.identifier,
            }]
        }]
    }
    assert data == expected


@pytest.mark.django_db
@pytest.mark.parametrize('show_admin_link', [True, False])
def test_plan_node(graphql_client_query_data, show_admin_link):
    plan = PlanWithRelatedObjectsFactory(show_admin_link=show_admin_link)
    admin_hostname = AdminHostnameFactory()
    client_plan = ClientPlanFactory(plan=plan, client=admin_hostname.client)
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $hostname: String!) {
          plan(id: $plan) {
            __typename
            actions {
              __typename
            }
            adminUrl
            categoryTypes {
              __typename
            }
            domain(hostname: $hostname) {
              __typename
            }
            id
            image {
              __typename
            }
            impactGroups {
              __typename
            }
            lastActionIdentifier
            mainMenu {
              __typename
            }
            pages {
              __typename
            }
            primaryLanguage
            serveFileBaseUrl
            footer {
              __typename
            }
          }
        }
        ''',
        variables={'plan': plan.identifier, 'hostname': plan.domains.first().hostname}
    )
    if show_admin_link:
        expected_admin_url = client_plan.client.get_admin_url()
    else:
        expected_admin_url = None
    expected = {
        'plan': {
            '__typename': 'Plan',
            'actions': [{
                '__typename': 'Action',
            }],
            'adminUrl': expected_admin_url,
            'categoryTypes': [{
                '__typename': 'CategoryType',
            }],
            'domain': {
                '__typename': 'PlanDomain',
            },
            'id': plan.identifier,
            'image': {
                '__typename': 'Image',
            },
            'impactGroups': [{
                '__typename': 'ImpactGroup',
            }],
            'lastActionIdentifier': plan.get_last_action_identifier(),
            'mainMenu': {
                '__typename': 'MainMenu',
            },
            'pages': [{
                '__typename': 'PlanRootPage',
            }],
            'primaryLanguage': get_default_language(),
            'serveFileBaseUrl': 'http://testserver',
            'footer': {
                '__typename': 'Footer',
            },
        }
    }
    assert data == expected
