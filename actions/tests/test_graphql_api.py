import pytest


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
        {
            plan(id: "''' f'{plan.identifier}' '''") {
                id
            }
        }
        ''',
    )
    assert data['plan']['id'] == plan.identifier
