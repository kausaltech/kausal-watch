import pytest

from orgs.models import Organization
from orgs.tests.factories import OrganizationFactory

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
    assert contains_error(
        response,
        message="Directive '@auth' argument 'token' of type 'String!' is required, but it was not provided."
    )


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
    assert contains_error(
        response,
        message="Directive '@auth' argument 'uuid' of type 'String!' is required, but it was not provided."
    )


def test_create_organization(graphql_client_query_data, uuid, token):
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


def test_create_organization_with_id_should_fail(graphql_client_query, contains_error, uuid, token):
    response = graphql_client_query(
        '''
        mutation($uuid: String!, $token: String!)
        @auth(uuid: $uuid, token: $token)
        {
          createOrganization(input: {id: 0, name: "test"}) {
            organization {
              id
            }
          }
        }
        ''',
        variables={'uuid': uuid, 'token': token}
    )
    assert contains_error(
        response,
        message="Field 'id' is not defined by type 'CreateOrganizationMutationInput'."
    )


def test_delete_organization_root(graphql_client_query_data, contains_error, uuid, token):
    org = OrganizationFactory()
    response = graphql_client_query_data(
        '''
        mutation($uuid: String!, $token: String!, $organization: ID!)
        @auth(uuid: $uuid, token: $token)
        {
          deleteOrganization(id: $organization) {
            ok
          }
        }
        ''',
        variables={'uuid': uuid, 'token': token, 'organization': str(org.id)}
    )
    assert response['deleteOrganization']['ok']
    assert not Organization.objects.filter(id=org.id).exists()


def test_delete_organization(graphql_client_query_data, uuid, token, organization):
    sub_org = OrganizationFactory(parent=organization)
    response = graphql_client_query_data(
        '''
        mutation($uuid: String!, $token: String!, $organization: ID!)
        @auth(uuid: $uuid, token: $token)
        {
          deleteOrganization(id: $organization) {
            ok
          }
        }
        ''',
        variables={'uuid': uuid, 'token': token, 'organization': str(sub_org.id)}
    )
    assert response['deleteOrganization']['ok']
    assert not Organization.objects.filter(id=sub_org.id).exists()


def test_update_organization(graphql_client_query_data, uuid, token, organization):
    assert organization.name != 'test'
    response = graphql_client_query_data(
        '''
        mutation($uuid: String!, $token: String!, $organization: ID!)
        @auth(uuid: $uuid, token: $token)
        {
          updateOrganization(input: {id: $organization, name: "test"}) {
            organization {
              id
              name
            }
          }
        }
        ''',
        variables={'uuid': uuid, 'token': token, 'organization': str(organization.id)}
    )
    assert response['updateOrganization']['organization']['id'] == str(organization.id)
    assert response['updateOrganization']['organization']['name'] == 'test'
    organization.refresh_from_db()
    assert organization.name == 'test'


def test_update_organization_without_id_should_fail(graphql_client_query, contains_error, uuid, token, organization):
    response = graphql_client_query(
        '''
        mutation($uuid: String!, $token: String!)
        @auth(uuid: $uuid, token: $token)
        {
          updateOrganization(input: {name: "test"}) {
            organization {
              id
            }
          }
        }
        ''',
        variables={'uuid': uuid, 'token': token}
    )
    assert contains_error(response, message='ID not specified')
