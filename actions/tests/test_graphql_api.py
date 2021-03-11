import pytest
from pytest_factoryboy import LazyFixture

from actions.models import CategoryTypeMetadata
from actions.tests.factories import (
    CategoryFactory, CategoryTypeFactory, CategoryMetadataRichTextFactory, CategoryTypeMetadataFactory,
    CategoryTypeMetadataChoiceFactory
)
from aplans.utils import hyphenate
from pages.models import CategoryPage


@pytest.fixture
def suborganization(organization_factory, organization):
    return organization_factory(parent=organization)


@pytest.fixture
def another_organization(organization_factory):
    return organization_factory()


@pytest.mark.django_db
def test_plan_nonexistent_domain(graphql_client_query_data):
    data = graphql_client_query_data(
        '''
        {
          plan(domain: "foo.localhost") {
            id
          }
        }
        ''',
    )
    assert data['plan'] is None


@pytest.mark.django_db
def test_plan_exists(graphql_client_query_data, plan):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            id
          }
        }
        ''',
        variables=dict(plan=plan.identifier)
    )
    assert data['plan']['id'] == plan.identifier


@pytest.mark.django_db
def test_plan_categories(graphql_client_query_data, plan, category_type):
    c0 = CategoryFactory(type=category_type)
    c1 = CategoryFactory(type=category_type, parent=c0)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            categoryTypes {
              id
              identifier
              name
              usableForActions
              categories {
                id
                identifier
                name
                parent {
                  id
                }
              }
            }
          }
        }
        ''',
        variables=dict(plan=plan.identifier)
    )
    expected = {
        'plan': {
            'categoryTypes': [{
                'id': str(category_type.id),
                'identifier': category_type.identifier,
                'name': category_type.name,
                'usableForActions': category_type.usable_for_actions,
                'categories': [{
                    'id': str(c0.id),
                    'identifier': c0.identifier,
                    'name': c0.name,
                    'parent': None
                }, {
                    'id': str(c1.id),
                    'identifier': c1.identifier,
                    'name': c1.name,
                    'parent': {
                        'id': str(c0.id)
                    }
                }]
            }]
        }
    }
    assert data == expected


@pytest.mark.django_db
def test_plan_actions(graphql_client_query_data, plan, action, action_schedule, category,
                      action_responsible_party):
    action.schedule.add(action_schedule)
    action.categories.add(category)
    action.responsible_parties.add(action_responsible_party)
    assert action.schedule.count() == 1
    schedule = action.schedule.first()
    assert action.categories.count() == 1
    category = action.categories.first()
    assert action.responsible_parties.count() == 1
    responsible_party = action.responsible_parties.first()
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          planActions(plan: $plan) {
            id
            identifier
            name(hyphenated: true)
            officialName
            completion
            plan {
              id
            }
            schedule {
              id
            }
            status {
              id
              identifier
              name
            }
            manualStatusReason
            implementationPhase {
              id
              identifier
              name
            }
            impact {
              id
              identifier
            }
            categories {
              id
            }
            responsibleParties {
              id
              organization {
                id
                abbreviation
                name
              }
            }
            mergedWith {
              id
              identifier
            }
          }
        }
        ''',
        variables=dict(plan=plan.identifier)
    )
    expected = {
        'planActions': [{
            'id': str(action.id),
            'identifier': action.identifier,
            'name': hyphenate(action.name),
            'officialName': action.official_name,
            'completion': action.completion,
            'plan': {
                'id': str(plan.identifier),  # TBD: Why not use the `id` field as we do for most other models?
            },
            'schedule': [{
                'id': str(schedule.id),
            }],
            'status': {
                'id': str(action.status.id),
                'identifier': action.status.identifier,
                'name': action.status.name,
            },
            'manualStatusReason': None,
            'implementationPhase': {
                'id': str(action.implementation_phase.id),
                'identifier': action.implementation_phase.identifier,
                'name': action.implementation_phase.name,
            },
            'impact': {
                'id': str(action.impact.id),
                'identifier': action.impact.identifier,
            },
            'categories': [{
                'id': str(category.id),
            }],
            'responsibleParties': [{
                'id': str(responsible_party.id),
                'organization': {
                    'id': str(action.plan.organization.id),
                    'abbreviation': action.plan.organization.abbreviation,
                    'name': action.plan.organization.name,
                },
            }],
            'mergedWith': None,
        }]
    }
    assert data == expected


@pytest.mark.django_db
@pytest.mark.parametrize('with_ancestors', [True, False])
@pytest.mark.parametrize('organization__parent', [LazyFixture('another_organization')])
def test_plan_organization(graphql_client_query_data, another_organization, organization, suborganization, plan,
                           action_responsible_party, with_ancestors):
    superorganization = another_organization
    assert plan.organization == organization
    assert organization.parent == another_organization
    assert list(organization.children.all()) == [suborganization]
    assert organization.classification is None
    assert suborganization.classification is None
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $withAncestors: Boolean!) {
          planOrganizations(plan: $plan, withAncestors: $withAncestors) {
            id
            abbreviation
            name
            classification {
              name
            }
            parent {
              id
            }
          }
        }
        ''',
        variables={
            'plan': plan.identifier,
            'withAncestors': with_ancestors,
        }
    )
    expected_organizations = []
    if with_ancestors:
        expected_organizations.append({
            'id': str(superorganization.id),
            'abbreviation': superorganization.abbreviation,
            'name': superorganization.name,
            'classification': None,
            'parent': None,
        })
    expected_organizations.append({
        'id': str(organization.id),
        'abbreviation': organization.abbreviation,
        'name': organization.name,
        'classification': None,
        'parent': {
            'id': superorganization.id,
        },
    })
    expected = {
        'planOrganizations': expected_organizations
    }
    assert data == expected


@pytest.mark.django_db
def test_categorymetadata_order_as_in_categorytypemetadata(graphql_client_query_data, plan, category, category_type):
    ctm0 = CategoryTypeMetadataFactory(type=category_type)
    ctm1 = CategoryTypeMetadataFactory(type=category_type)
    assert ctm0.order < ctm1.order
    cmrt0 = CategoryMetadataRichTextFactory(metadata=ctm0, category=category)
    cmrt1 = CategoryMetadataRichTextFactory(metadata=ctm1, category=category)
    category_page = CategoryPage(title='Category', slug='category-slug', category=category)
    plan.root_page.add_child(instance=category_page)

    query = '''
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            ... on CategoryPage {
              category {
                metadata {
                  ... on CategoryMetadataRichText {
                    keyIdentifier
                    value
                  }
                }
              }
            }
          }
        }
        '''
    query_variables = {
        'plan': category_page.category.type.plan.identifier,
        'path': f'/{category.identifier}-category-slug',
    }
    expected = {
        'planPage': {
            'category': {
                'metadata': [{
                    'keyIdentifier': ctm0.identifier,
                    'value': cmrt0.text,
                }, {
                    'keyIdentifier': ctm1.identifier,
                    'value': cmrt1.text,
                }],
            }
        }
    }
    data = graphql_client_query_data(query, variables=query_variables)
    assert data == expected

    ctm0.order, ctm1.order = ctm1.order, ctm0.order
    ctm0.save()
    ctm1.save()
    expected_metadata = expected['planPage']['category']['metadata']
    expected_metadata[0], expected_metadata[1] = expected_metadata[1], expected_metadata[0]
    data = graphql_client_query_data(query, variables=query_variables)
    assert data == expected


@pytest.mark.django_db
def test_category_types(graphql_client_query_data, plan):
    ct = CategoryTypeFactory(plan=plan)
    ctm1 = CategoryTypeMetadataFactory(type=ct)
    ctm2 = CategoryTypeMetadataFactory(type=ct, format=CategoryTypeMetadata.MetadataFormat.ORDERED_CHOICE)
    ctm2c1 = CategoryTypeMetadataChoiceFactory(metadata=ctm2)
    ctm2c2 = CategoryTypeMetadataChoiceFactory(metadata=ctm2)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
            plan(id: $plan) {
                categoryTypes {
                    identifier
                    name
                    metadata {
                        format
                        identifier
                        name
                        choices {
                            identifier
                            name
                        }
                    }
                }
            }
        }
        ''',
        variables=dict(plan=plan.identifier)
    )
    expected = {
        'plan': {
            'categoryTypes': [{
                'identifier': ct.identifier,
                'name': ct.name,
                'metadata': [{
                    'format': 'RICH_TEXT',
                    'identifier': ctm1.identifier,
                    'name': ctm1.name,
                    'choices': [],
                }, {
                    'format': 'ORDERED_CHOICE',
                    'identifier': ctm2.identifier,
                    'name': ctm2.name,
                    'choices': [{
                        'identifier': ctm2c1.identifier,
                        'name': ctm2c1.name,
                    }, {
                        'identifier': ctm2c2.identifier,
                        'name': ctm2c2.name,
                    }],
                }],
            }]
        }
    }
    assert data == expected
