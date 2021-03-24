import pytest

from actions.models import get_default_language, CategoryTypeMetadata
from actions.tests.factories import (
    ActionFactory, CategoryFactory, CategoryLevelFactory, CategoryMetadataChoiceFactory,
    CategoryMetadataRichTextFactory, CategoryTypeFactory, CategoryTypeMetadataFactory,
    CategoryTypeMetadataChoiceFactory, ImpactGroupFactory, ImpactGroupActionFactory, PlanFactory, ScenarioFactory
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
    plan = PlanFactory(show_admin_link=show_admin_link)
    action = ActionFactory(plan=plan)
    category_type = CategoryTypeFactory(plan=plan)
    # Switch off RelatedFactory _action because it would generate an extra action
    impact_group = ImpactGroupFactory(plan=plan, _action=None)
    ImpactGroupActionFactory(group=impact_group, action=action)
    admin_hostname = AdminHostnameFactory()
    client_plan = ClientPlanFactory(plan=plan, client=admin_hostname.client)
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $hostname: String!) {
          plan(id: $plan) {
            __typename
            actions {
              __typename
              id
            }
            adminUrl
            categoryTypes {
              __typename
              id
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
              id
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
                'id': str(action.id),
            }],
            'adminUrl': expected_admin_url,
            'categoryTypes': [{
                '__typename': 'CategoryType',
                'id': str(category_type.id),
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
                'id': str(impact_group.id),
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


@pytest.mark.django_db
def test_category_type_metadata_choice_node(
    graphql_client_query_data, plan, category_type_metadata_choice, category_metadata_choice
):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            type {
              metadata {
                choices {
                  identifier
                  name
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
                    'choices': [{
                        'identifier': category_type_metadata_choice.identifier,
                        'name': category_type_metadata_choice.name,
                    }],
                }]
            }
        }]
    }
    assert data == expected


@pytest.mark.django_db
def test_category_type_node(
    graphql_client_query_data, plan, category_type, category, category_level, category_type_metadata__rich_text
):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            type {
              id
              plan {
                __typename
                # Workaround: I just want __typename, but this causes an error due to graphene-django-optimizer.
                identifier
              }
              name
              identifier
              usableForActions
              usableForIndicators
              editableForActions
              editableForIndicators
              levels {
                __typename
              }
              categories {
                __typename
              }
              metadata {
                __typename
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
                'id': str(category_type.id),
                'plan': {
                    '__typename': 'Plan',
                    'identifier': plan.identifier,
                },
                'name': category_type.name,
                'identifier': category_type.identifier,
                'usableForActions': category_type.usable_for_actions,
                'usableForIndicators': category_type.usable_for_indicators,
                'editableForActions': category_type.editable_for_actions,
                'editableForIndicators': category_type.editable_for_indicators,
                'levels': [{
                    '__typename': 'CategoryLevel'
                }],
                'categories': [{
                    '__typename': 'Category'
                }],
                'metadata': [{
                    '__typename': 'CategoryTypeMetadata'
                }],
            }
        }]
    }
    assert data == expected


@pytest.mark.django_db
def test_category_node(
    graphql_client_query_data, plan, category_type, category, category_level, category_metadata_rich_text,
    category_metadata_choice
):
    child_category = CategoryFactory(parent=category)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planCategories(plan: $plan) {
            id
            type {
              __typename
            }
            order
            identifier
            name
            parent {
              __typename
            }
            shortDescription
            color
            children {
              __typename
              id
              parent {
                __typename
                id
              }
            }
            categoryPage {
              __typename
            }
            image {
              __typename
            }
            metadata {
              __typename
            }
            level {
              __typename
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'planCategories': [{
            'id': str(category.id),
            'type': {
              '__typename': 'CategoryType',
            },
            'order': 1,
            'identifier': category.identifier,
            'name': category.name,
            'parent': None,
            'shortDescription': category.short_description,
            'color': category.color,
            'children': [{
                '__typename': 'Category',
                'id': str(child_category.id),
                'parent': {
                  '__typename': 'Category',
                  'id': str(category.id),
                }
            }],
            'categoryPage': {
                '__typename': 'CategoryPage',
            },
            'image': {
                '__typename': 'Image',
            },
            'metadata': [{
                '__typename': 'CategoryMetadataRichText',
            }, {
                '__typename': 'CategoryMetadataChoice',
            }],
            'level': {
                '__typename': 'CategoryLevel',
            },
        }]
    }
    assert data == expected


@pytest.mark.django_db
def test_scenario_node(graphql_client_query_data):
    scenario = ScenarioFactory()
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            scenarios {
              id
              plan {
                __typename
              }
              name
              identifier
              description
            }
          }
        }
        ''',
        variables={'plan': scenario.plan.identifier}
    )
    expected = {
        'plan': {
            'scenarios': [{
                'id': str(scenario.id),
                'plan': {
                    '__typename': 'Plan',
                },
                'name': scenario.name,
                'identifier': scenario.identifier,
                'description': scenario.description,
            }]
        }
    }
    assert data == expected


@pytest.mark.django_db
def test_impact_group_node(graphql_client_query_data):
    impact_group = ImpactGroupFactory()
    impact_group_child = ImpactGroupFactory(plan=impact_group.plan, parent=impact_group)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            impactGroups {
              id
              plan {
                __typename
                id
              }
              identifier
              parent {
                __typename
                id
              }
              weight
              color
              actions {
                __typename
              }
              name
            }
          }
        }
        ''',
        variables={'plan': impact_group.plan.identifier}
    )
    expected = {
        'plan': {
            'impactGroups': [{
                'id': str(impact_group.id),
                'plan': {
                    '__typename': 'Plan',
                    'id': impact_group.plan.identifier,
                },
                'identifier': impact_group.identifier,
                'parent': None,
                'weight': impact_group.weight,
                'color': impact_group.color,
                'actions': [{
                    '__typename': 'ImpactGroupAction',
                }],
                'name': impact_group.name,
            }, {
                'id': str(impact_group_child.id),
                'plan': {
                    '__typename': 'Plan',
                    'id': impact_group_child.plan.identifier,
                },
                'identifier': impact_group_child.identifier,
                'parent': {
                    '__typename': 'ImpactGroup',
                    'id': str(impact_group.id),
                },
                'weight': impact_group_child.weight,
                'color': impact_group_child.color,
                'actions': [{
                    '__typename': 'ImpactGroupAction',
                }],
                'name': impact_group_child.name,
            }]
        }
    }
    assert data == expected
