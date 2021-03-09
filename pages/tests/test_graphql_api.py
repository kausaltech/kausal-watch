import json
import pytest

from pages.models import StaticPage


def expected_menu_item_for_page(page):
    return {
        'id': str(page.id),
        'linkText': page.title,
        'page': {
            # We strip the trailing slash of url_path in pages/apps.py
            'urlPath': page.url_path.rstrip('/'),
            'slug': page.slug,
        },
    }


def menu_query(menu_field='mainMenu', with_descendants=False):
    if with_descendants:
        items = 'items(withDescendants: true)'
    else:
        items = 'items(withDescendants: false)'
    return '''
        query($plan: ID!) {
          plan(id: $plan) {
            ''' + menu_field + ''' {
              ''' + items + ''' {
                id
                linkText
                page {
                  urlPath
                  slug
                }
              }
            }
          }
        }
        '''


def add_menu_test_pages(root_page, menu_key='show_in_menus'):
    # Build hierarchy:
    # root_page
    #   page_not_in_menu
    #     subpage1_in_menu (should be shown if and only if we set the parameter `with_descendants` to true)
    #   page1_in_menu
    #     subpage_not_in_menu
    #     subpage2_in_menu (should be shown if and only if we set the parameter `with_descendants` to true)
    #   page2_in_menu
    pages = {}

    pages['page_not_in_menu'] = StaticPage(title="Page not in menu")
    root_page.add_child(instance=pages['page_not_in_menu'])

    pages['subpage1_in_menu'] = StaticPage(title="Subpage 1 in menu", **{menu_key: True})
    pages['page_not_in_menu'].add_child(instance=pages['subpage1_in_menu'])

    pages['page1_in_menu'] = StaticPage(title="Page 1 in menu", **{menu_key: True})
    root_page.add_child(instance=pages['page1_in_menu'])

    pages['subpage_not_in_menu'] = StaticPage(title="Subpage not in menu")
    pages['page1_in_menu'].add_child(instance=pages['subpage_not_in_menu'])

    pages['subpage2_in_menu'] = StaticPage(title="Subpage 2 in menu", **{menu_key: True})
    pages['page1_in_menu'].add_child(instance=pages['subpage2_in_menu'])

    pages['page2_in_menu'] = StaticPage(title="Page 2 in menu", **{menu_key: True})
    root_page.add_child(instance=pages['page2_in_menu'])

    return pages


@pytest.mark.django_db
def test_plan_root_page_exists(graphql_client_query_data, plan):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            pages {
              ... on PlanRootPage {
                id
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier},
    )
    pages = data['plan']['pages']
    assert len(pages) == 1
    page = pages[0]
    assert page['id'] == str(plan.root_page.id)


@pytest.mark.django_db
def test_plan_root_page_contains_block(graphql_client_query_data, plan):
    hero_data = {'layout': 'big_image', 'heading': 'foo', 'lead': 'bar'}
    plan.root_page.body = json.dumps([
        {'type': 'front_page_hero', 'value': hero_data},
    ])
    plan.root_page.save()
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            pages {
              ... on PlanRootPage {
                body {
                  ... on FrontPageHeroBlock {
                    ''' f'{" ".join(hero_data.keys())}' '''
                  }
                }
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier},
    )
    pages = data['plan']['pages']
    assert len(pages) == 1
    blocks = pages[0]['body']
    assert len(blocks) == 1
    block = blocks[0]
    for key, value in hero_data.items():
        assert block[key] == value


@pytest.mark.django_db
@pytest.mark.parametrize('menu_field,menu_key,with_descendants,expected_pages', [
    ('mainMenu', 'show_in_menus', False, ['page1_in_menu', 'page2_in_menu']),
    ('mainMenu', 'show_in_menus', True, ['subpage1_in_menu', 'page1_in_menu', 'subpage2_in_menu', 'page2_in_menu']),
    ('footer', 'show_in_footer', False, ['page1_in_menu', 'page2_in_menu']),
    ('footer', 'show_in_footer', True, ['subpage1_in_menu', 'page1_in_menu', 'subpage2_in_menu', 'page2_in_menu']),
])
def test_main_menu(graphql_client_query_data, plan, menu_field, menu_key, with_descendants, expected_pages):
    pages = add_menu_test_pages(plan.root_page, menu_key)

    data = graphql_client_query_data(
        menu_query(menu_field, with_descendants),
        variables={'plan': plan.identifier},
    )
    expected = {
        'plan': {
            menu_field: {
                'items': [expected_menu_item_for_page(pages[page_name]) for page_name in expected_pages]
            }
        }
    }
    assert data == expected
