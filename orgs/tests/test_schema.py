import pytest

from orgs.models import Organization
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_create_organization_missing_token(graphql_client_query, contains_error, uuid):
    response = graphql_client_query(
        '''
        mutation($uuid: String!)
        @auth(uuid: $uuid)
        {
          createOrganization(input: {name: "test"}) {
            organization {
              id
            }
          }
        }
        ''',
        variables={'uuid': uuid}
    )
    assert contains_error(response,
                          message='Directive "auth" argument "token" of type "String!" is required but not provided.')


def test_create_organization_missing_uuid(graphql_client_query, contains_error, token):
    response = graphql_client_query(
        '''
        mutation($token: String!)
        @auth(token: $token)
        {
          createOrganization(input: {name: "test"}) {
            organization {
              id
            }
          }
        }
        ''',
        variables={'token': token}
    )
    assert contains_error(response,
                          message='Directive "auth" argument "uuid" of type "String!" is required but not provided.')


def test_create_organization(graphql_client_query_data, contains_error, uuid, token):
    response = graphql_client_query_data(
        '''
        mutation($uuid: String!, $token: String!)
        @auth(uuid: $uuid, token: $token)
        {
          createOrganization(input: {name: "test"}) {
            organization {
              id
            }
          }
        }
        ''',
        variables={'uuid': uuid, 'token': token}
    )
    org = Organization.objects.get(id=response['createOrganization']['organization']['id'])
    assert org.name == 'test'
