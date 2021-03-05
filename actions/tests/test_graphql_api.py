import pytest

from actions.tests.factories import CategoryMetadataRichTextFactory, CategoryTypeMetadataFactory
from pages.models import CategoryPage


@pytest.mark.django_db
def test_plan_does_not_exist(graphql_client_query_data):
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
        variables={'plan': plan.identifier},
    )
    assert data['plan']['id'] == plan.identifier


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
