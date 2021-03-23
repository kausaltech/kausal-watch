import pytest

from actions.models import get_default_language, CategoryTypeMetadata
from actions.tests.factories import (
    CategoryFactory, CategoryLevelFactory, CategoryMetadataChoiceFactory, CategoryMetadataRichTextFactory,
    CategoryTypeFactory, CategoryTypeMetadataFactory, CategoryTypeMetadataChoiceFactory, PlanFactory,
    PlanWithRelatedObjectsFactory
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


@pytest.mark.django_db
def test_category_metadata_choice_node(graphql_client_query_data):
    plan = PlanFactory()
    ct = CategoryTypeFactory(plan=plan)
    ctm = CategoryTypeMetadataFactory(type=ct, format=CategoryTypeMetadata.MetadataFormat.ORDERED_CHOICE)
    ctmc = CategoryTypeMetadataChoiceFactory(metadata=ctm)
    # Create a category with metadata so we can access the CategoryMetadataChoiceNode via planCategories
    category = CategoryFactory(type=ct)
    cmc = CategoryMetadataChoiceFactory(metadata=ctm, category=category, choice=ctmc)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            metadata {
              ... on CategoryMetadataChoice {
                id
                metadata {
                  __typename
                }
                category {
                  __typename
                }
                choice {
                  __typename
                }
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
                'id': str(cmc.id),
                'metadata': {
                    '__typename': 'CategoryTypeMetadata',
                },
                'category': {
                    '__typename': 'Category',
                },
                'choice': {
                    '__typename': 'CategoryTypeMetadataChoice',
                },
                'key': ctm.name,
                'keyIdentifier': ctm.identifier,
                'value': ctmc.name,
                'valueIdentifier': ctmc.identifier,
            }]
        }]
    }
    assert data == expected


@pytest.mark.django_db
def test_category_metadata_rich_text_node(graphql_client_query_data):
    plan = PlanFactory()
    ct = CategoryTypeFactory(plan=plan)
    ctm = CategoryTypeMetadataFactory(type=ct, format=CategoryTypeMetadata.MetadataFormat.RICH_TEXT)
    # Create a category with metadata so we can access the CategoryMetadataRichTextNode via planCategories
    category = CategoryFactory(type=ct)
    cmrt = CategoryMetadataRichTextFactory(metadata=ctm, category=category)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            metadata {
              ... on CategoryMetadataRichText {
                id
                metadata {
                  __typename
                }
                category {
                  __typename
                }
                key
                keyIdentifier
                value
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
                'id': str(cmrt.id),
                'metadata': {
                    '__typename': 'CategoryTypeMetadata',
                },
                'category': {
                    '__typename': 'Category',
                },
                'key': ctm.name,
                'keyIdentifier': ctm.identifier,
                'value': cmrt.text,
            }]
        }]
    }
    assert data == expected


@pytest.mark.django_db
def test_category_level_node(graphql_client_query_data):
    plan = PlanFactory()
    ct = CategoryTypeFactory(plan=plan)
    level = CategoryLevelFactory(type=ct)
    # Create a category with metadata so we can access the CategoryMetadataRichTextNode via planCategories
    CategoryFactory(type=ct)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            level {
              ... on CategoryLevel {
                id
                order
                type {
                  __typename
                }
                name
                namePlural
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'level': {
                'id': str(level.id),
                'order': 1,
                'type': {
                    '__typename': 'CategoryType',
                },
                'name': level.name,
                'namePlural': level.name_plural,
            }
        }]
    }
    assert data == expected
