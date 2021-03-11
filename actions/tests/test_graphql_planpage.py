import pytest

from pages.models import CategoryPage


@pytest.mark.django_db
def test_categorymetadata_order_as_in_categorytypemetadata(
    graphql_client_query_data, plan, category, category_type, category_type_metadata_factory,
    category_metadata_rich_text_factory
):
    ctm0 = category_type_metadata_factory(type=category_type)
    ctm1 = category_type_metadata_factory(type=category_type)
    assert ctm0.order < ctm1.order
    cmrt0 = category_metadata_rich_text_factory(metadata=ctm0, category=category)
    cmrt1 = category_metadata_rich_text_factory(metadata=ctm1, category=category)
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


