import json
import pytest

from actions.models import AttributeType
from pages.models import StaticPage
from admin_site.tests.factories import ClientPlanFactory

pytestmark = pytest.mark.django_db


def expected_menu_item_for_page(page):
    return {
        'id': str(page.id),
        'page': {
            'title': page.title,
            # We strip the trailing slash of url_path in pages/apps.py
            'urlPath': page.url_path.rstrip('/'),
            'slug': page.slug,
        },
    }


def menu_query(menu_field='mainMenu', with_descendants=False):
    if with_descendants:
        with_descendants_str = 'true'
    else:
        with_descendants_str = 'false'
    return '''
        query($plan: ID!) {
          plan(id: $plan) {
            %(menu)s {
              items(withDescendants: %(with_descendants_str)s) {
                ... on PageMenuItem {
                    id
                    page {
                      title
                      urlPath
                      slug
                    }
                }
              }
            }
          }
        }
        ''' % {'menu': menu_field, 'with_descendants_str': with_descendants_str}


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


@pytest.fixture
def suborganization(organization_factory, organization):
    return organization_factory(parent=organization)


@pytest.fixture
def another_organization(organization_factory):
    return organization_factory()


def test_nonexistent_domain(graphql_client_query_data):
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


@pytest.mark.parametrize('show_admin_link', [True, False])
def test_plan_admin_url(graphql_client_query_data, plan, show_admin_link):
    client_plan = ClientPlanFactory(plan=plan)
    plan.features.show_admin_link = show_admin_link
    plan.features.save()
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            adminUrl
          }
        }
        ''',
        variables=dict(plan=plan.identifier)
    )
    if show_admin_link:
        admin_url = f'https://{client_plan.client.admin_hostnames.first().hostname}'
        assert data == {'plan': {'adminUrl': admin_url}}
    else:
        assert data == {'plan': {'adminUrl': None}}


def test_categorytypes(graphql_client_query_data, plan, category_type, category_factory):
    c0 = category_factory(type=category_type)
    c1 = category_factory(type=category_type, parent=c0)
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


def test_category_types(
    graphql_client_query_data, plan, category_type_factory, attribute_type_factory,
    attribute_type_choice_option_factory
):
    ct = category_type_factory(plan=plan)
    cat1 = attribute_type_factory(scope=ct)
    cat2 = attribute_type_factory(scope=ct,
                                  format=AttributeType.AttributeFormat.ORDERED_CHOICE)
    cat2co1 = attribute_type_choice_option_factory(type=cat2)
    cat2co2 = attribute_type_choice_option_factory(type=cat2)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
            plan(id: $plan) {
                categoryTypes {
                    identifier
                    name
                    attributeTypes {
                        format
                        identifier
                        name
                        choiceOptions {
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
                'attributeTypes': [{
                    'format': 'RICH_TEXT',
                    'identifier': cat1.identifier,
                    'name': cat1.name,
                    'choiceOptions': [],
                }, {
                    'format': 'ORDERED_CHOICE',
                    'identifier': cat2.identifier,
                    'name': cat2.name,
                    'choiceOptions': [{
                        'identifier': cat2co1.identifier,
                        'name': cat2co1.name,
                    }, {
                        'identifier': cat2co2.identifier,
                        'name': cat2co2.name,
                    }],
                }],
            }]
        }
    }
    assert data == expected


def test_plan_root_page_exists(graphql_client_query_data, plan):
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            pages {
              __typename
              ... on PlanRootPage {
                id
              }
            }
          }
        }
        ''',
        variables=dict(plan=plan.identifier)
    )
    pages = data['plan']['pages']
    assert any(page['__typename'] == 'PlanRootPage' and page['id'] == str(plan.root_page.id) for page in pages)


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
              __typename
              ... on PlanRootPage {
                body {
                  ... on FrontPageHeroBlock {
                    %s
                  }
                }
              }
            }
          }
        }
        ''' % " ".join(hero_data.keys()),
        variables=dict(plan=plan.identifier)
    )
    pages = data['plan']['pages']
    page = next(page for page in pages if page['__typename'] == 'PlanRootPage')
    blocks = page['body']
    assert len(blocks) == 1
    block = blocks[0]
    for key, value in hero_data.items():
        assert block[key] == value


@pytest.mark.parametrize('menu_field,menu_key,with_descendants,expected_pages', [
    ('mainMenu', 'show_in_menus', False, ['page1_in_menu', 'page2_in_menu']),
    ('mainMenu', 'show_in_menus', True, ['subpage1_in_menu', 'page1_in_menu', 'subpage2_in_menu', 'page2_in_menu']),
    ('footer', 'show_in_footer', False, ['page1_in_menu', 'page2_in_menu']),
    ('footer', 'show_in_footer', True, ['subpage1_in_menu', 'page1_in_menu', 'subpage2_in_menu', 'page2_in_menu']),
])
def test_menu(graphql_client_query_data, plan, menu_field, menu_key, with_descendants, expected_pages):
    # Some pages (e.g., action and indicator list) are in menus and footers by default; remove for this test
    for page in plan.root_page.get_children().specific():
        page.show_in_menus = False
        page.show_in_footer = False
        page.save()
    pages = add_menu_test_pages(plan.root_page, menu_key)
    data = graphql_client_query_data(
        menu_query(menu_field, with_descendants),
        variables=dict(plan=plan.identifier)
    )
    expected = {
        'plan': {
            menu_field: {
                'items': [expected_menu_item_for_page(pages[page_name]) for page_name in expected_pages]
            }
        }
    }
    assert data == expected


def test_footer_children_only_shown(graphql_client_query_data, plan):
    # Some pages (e.g., action and indicator list) are in menus and footers by default; remove for this test
    for page in plan.root_page.get_children().specific():
        page.show_in_footer = False
        page.save()
    page1 = StaticPage(title="page1", show_in_footer=True)
    plan.root_page.add_child(instance=page1)
    page2 = StaticPage(title="page2", show_in_footer=True)
    page3 = StaticPage(title="page3", show_in_footer=False)
    page1.add_child(instance=page2)
    page1.add_child(instance=page3)
    data = graphql_client_query_data(
        '''
        query($plan: ID!) {
          plan(id: $plan) {
            footer {
              items {
                ... on PageMenuItem {
                    id
                    children {
                      id
                    }
                }
              }
            }
          }
        }
        ''',
        variables={'plan': plan.identifier}
    )
    expected = {
        'plan': {
            'footer': {
                'items': [{
                    'id': str(page1.id),
                    'children': [{
                        'id': str(page2.id),
                    }],
                }]
            }
        }
    }
    assert data == expected
