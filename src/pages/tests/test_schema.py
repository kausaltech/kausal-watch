import pytest

pytestmark = pytest.mark.django_db

PLAN_PAGE_QUERY = """
    query($plan: ID!, $path: String!) {
      planPage(plan: $plan, path: $path) {
        id
      }
    }
"""


def test_plan_page_path_with_nul_byte_returns_null(graphql_client_query_data, plan_with_pages):
    data = graphql_client_query_data(
        PLAN_PAGE_QUERY,
        variables={'plan': plan_with_pages.identifier, 'path': '/foo\x00bar'},
    )
    assert data == {'planPage': None}


def test_plan_page_root_path_returns_page(graphql_client_query_data, plan_with_pages):
    data = graphql_client_query_data(
        PLAN_PAGE_QUERY,
        variables={'plan': plan_with_pages.identifier, 'path': '/'},
    )
    assert data == {'planPage': {'id': str(plan_with_pages.root_page.id)}}
