import pytest

from pages.tests.factories import StaticPageFactory

pytestmark = pytest.mark.django_db


def test_adaptive_embed_block_title_and_description(graphql_client_query_data, plan_with_pages):
    plan = plan_with_pages
    root_page = plan.site.root_page
    slug = 'embed-test'
    static_page = StaticPageFactory.create(slug=slug, parent=root_page)
    static_page.body.append((
        'embed',
        {
            'title': 'Test embed title',
            'description': 'Test embed description',
            'embed': {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'height': 'm'},
            'full_width': False,
        },
    ))
    static_page.save()

    data = graphql_client_query_data(
        """
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            ... on StaticPage {
              body {
                ... on AdaptiveEmbedBlock {
                  title
                  description
                  fullWidth
                }
              }
            }
          }
        }
        """,
        variables=dict(plan=plan.identifier, path=f'/{slug}'),
    )

    blocks = data['planPage']['body']
    embed_block = blocks[-1]
    assert embed_block['title'] == 'Test embed title'
    assert embed_block['description'] == 'Test embed description'
    assert embed_block['fullWidth'] is False


def test_adaptive_embed_block_empty_title_and_description(graphql_client_query_data, plan_with_pages):
    plan = plan_with_pages
    root_page = plan.site.root_page
    slug = 'embed-test-empty'
    static_page = StaticPageFactory.create(slug=slug, parent=root_page)
    static_page.body.append((
        'embed',
        {
            'title': '',
            'description': '',
            'embed': {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'height': 's'},
            'full_width': True,
        },
    ))
    static_page.save()

    data = graphql_client_query_data(
        """
        query($plan: ID!, $path: String!) {
          planPage(plan: $plan, path: $path) {
            ... on StaticPage {
              body {
                ... on AdaptiveEmbedBlock {
                  title
                  description
                  fullWidth
                }
              }
            }
          }
        }
        """,
        variables=dict(plan=plan.identifier, path=f'/{slug}'),
    )

    blocks = data['planPage']['body']
    embed_block = blocks[-1]
    assert embed_block['title'] == ''
    assert embed_block['description'] == ''
    assert embed_block['fullWidth'] is True
