import pytest

from actions.models import get_default_language, CategoryTypeMetadata
from actions.tests.factories import (
    CategoryFactory, CategoryLevelFactory, CategoryMetadataChoiceFactory, CategoryMetadataRichTextFactory,
    CategoryTypeFactory, CategoryTypeMetadataFactory, CategoryTypeMetadataChoiceFactory, PlanFactory,
    PlanWithRelatedObjectsFactory
)
from admin_site.tests.factories import AdminHostnameFactory, ClientPlanFactory


@pytest.fixture
def plan():
    return PlanFactory()


@pytest.fixture
def category_type(plan):
    return CategoryTypeFactory(plan=plan)


@pytest.fixture
def category_type_metadata__rich_text(category_type):
    return CategoryTypeMetadataFactory(type=category_type, format=CategoryTypeMetadata.MetadataFormat.RICH_TEXT)


@pytest.fixture
def category_type_metadata__ordered_choice(category_type):
    return CategoryTypeMetadataFactory(type=category_type, format=CategoryTypeMetadata.MetadataFormat.ORDERED_CHOICE)


@pytest.fixture
def category_type_metadata_choice(category_type_metadata__ordered_choice):
    return CategoryTypeMetadataChoiceFactory(metadata=category_type_metadata__ordered_choice)


@pytest.fixture
def category_metadata_rich_text(category_type_metadata__rich_text, category):
    return CategoryMetadataRichTextFactory(metadata=category_type_metadata__rich_text, category=category)


@pytest.fixture
def category_metadata_choice(category_type_metadata__ordered_choice, category, category_type_metadata_choice):
    return CategoryMetadataChoiceFactory(metadata=category_type_metadata__ordered_choice,
                                         category=category,
                                         choice=category_type_metadata_choice)


@pytest.fixture
def category(category_type):
    return CategoryFactory(type=category_type)


@pytest.fixture
def category_level(category_type):
    return CategoryLevelFactory(type=category_type)


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
def test_category_metadata_choice_node(
    graphql_client_query_data, plan, category_metadata_choice, category_type_metadata__ordered_choice,
    category_type_metadata_choice
):
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
                'id': str(category_metadata_choice.id),
                'metadata': {
                    '__typename': 'CategoryTypeMetadata',
                },
                'category': {
                    '__typename': 'Category',
                },
                'choice': {
                    '__typename': 'CategoryTypeMetadataChoice',
                },
                'key': category_type_metadata__ordered_choice.name,
                'keyIdentifier': category_type_metadata__ordered_choice.identifier,
                'value': category_type_metadata_choice.name,
                'valueIdentifier': category_type_metadata_choice.identifier,
            }]
        }]
    }
    assert data == expected


@pytest.mark.django_db
def test_category_metadata_rich_text_node(
    graphql_client_query_data, plan, category_metadata_rich_text, category_type_metadata__rich_text
):
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
                'id': str(category_metadata_rich_text.id),
                'metadata': {
                    '__typename': 'CategoryTypeMetadata',
                },
                'category': {
                    '__typename': 'Category',
                },
                'key': category_type_metadata__rich_text.name,
                'keyIdentifier': category_type_metadata__rich_text.identifier,
                'value': category_metadata_rich_text.text,
            }]
        }]
    }
    assert data == expected


@pytest.mark.django_db
def test_category_level_node(graphql_client_query_data, plan, category_level, category):
    # We need to include the `category` fixture so we can access the CategoryLevelNode via planCategories
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
                'id': str(category_level.id),
                'order': 1,
                'type': {
                    '__typename': 'CategoryType',
                },
                'name': category_level.name,
                'namePlural': category_level.name_plural,
            }
        }]
    }
    assert data == expected


@pytest.mark.django_db
def test_category_type_metadata_node(
    graphql_client_query_data, plan, category_metadata_rich_text, category_metadata_choice,
    category_type_metadata__rich_text, category_type_metadata__ordered_choice
):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            type {
              metadata {
                identifier
                name
                format
                choices {
                  __typename
                }
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'type': {
                'metadata': [{
                    'identifier': category_type_metadata__rich_text.identifier,
                    'name': category_type_metadata__rich_text.name,
                    'format': 'RICH_TEXT',
                    'choices': [],
                }, {
                    'identifier': category_type_metadata__ordered_choice.identifier,
                    'name': category_type_metadata__ordered_choice.name,
                    'format': 'ORDERED_CHOICE',
                    'choices': [{
                        '__typename': 'CategoryTypeMetadataChoice',
                    }],
                }]
            }
        }]
    }
    assert data == expected
