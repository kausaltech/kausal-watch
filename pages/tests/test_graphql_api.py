import json
import pytest


@pytest.mark.django_db
def test_plan_root_page_exists(graphql_client_query_data, plan):
    data = graphql_client_query_data(
        '''
        {
            plan(id: "''' f'{plan.identifier}' '''") {
                pages {
                    ... on PlanRootPage {
                        id
                    }
                }
            }
        }
        ''',
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
        {
            plan(id: "''' f'{plan.identifier}' '''") {
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
    )
    pages = data['plan']['pages']
    assert len(pages) == 1
    blocks = pages[0]['body']
    assert len(blocks) == 1
    block = blocks[0]
    for key, value in hero_data.items():
        assert block[key] == value
