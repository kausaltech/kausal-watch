from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kausal_common.strawberry.mutations import OP_INFO_FRAGMENT
from kausal_common.testing.graphql import OperationMessage, assert_operation_errors

from orgs.models import Organization

if TYPE_CHECKING:
    from users.models import User

pytestmark = pytest.mark.django_db


# -- Mutation query strings --------------------------------------------------

CREATE_ORGANIZATION = (
    """
    mutation($input: OrganizationInput!) {
        organization {
            createOrganization(input: $input) {
                ... on Organization {
                    id
                    name
                    abbreviation
                    parent { id }
                }
                ... OpInfo
            }
        }
    }
"""
    + OP_INFO_FRAGMENT
)


# -- Permission tests --------------------------------------------------------


class TestOrganizationMutationPermissions:
    def test_requires_authentication(self, graphql_client_query):
        response = graphql_client_query(
            CREATE_ORGANIZATION,
            variables={'input': {'name': 'Test Org'}},
        )
        assert 'errors' in response

    def test_requires_superuser(self, graphql_client_query, client, user: User):
        client.force_login(user)
        response = graphql_client_query(
            CREATE_ORGANIZATION,
            variables={'input': {'name': 'Test Org'}},
        )
        assert 'errors' in response


# -- create_organization -----------------------------------------------------


class TestCreateOrganization:
    def test_create_root_organization(self, graphql_client_query_data, client, superuser: User):
        client.force_login(superuser)
        data = graphql_client_query_data(
            CREATE_ORGANIZATION,
            variables={
                'input': {
                    'name': 'Orbital Datacenter Authority',
                    'abbreviation': 'ODA',
                }
            },
        )
        result = data['organization']['createOrganization']
        assert result['name'] == 'Orbital Datacenter Authority'
        assert result['abbreviation'] == 'ODA'
        assert result['parent'] is None
        assert Organization.objects.filter(name='Orbital Datacenter Authority').exists()

    def test_create_child_organization(self, graphql_client_query_data, client, superuser: User):
        client.force_login(superuser)
        # Create a root org first
        parent = Organization.add_root(name='Parent Corp')

        data = graphql_client_query_data(
            CREATE_ORGANIZATION,
            variables={
                'input': {
                    'name': 'Child Division',
                    'parentId': str(parent.pk),
                }
            },
        )
        result = data['organization']['createOrganization']
        assert result['name'] == 'Child Division'
        assert result['parent']['id'] == str(parent.pk)

        child = Organization.objects.get(pk=result['id'])
        parent_obj = child.get_parent()
        assert parent_obj is not None
        assert parent_obj.pk == parent.pk

    def test_create_organization_with_invalid_parent(self, graphql_client_query, client, superuser: User):
        client.force_login(superuser)
        response = graphql_client_query(
            CREATE_ORGANIZATION,
            variables={
                'input': {
                    'name': 'Orphan Org',
                    'parentId': '999999',
                }
            },
        )
        data = response['data']['organization']['createOrganization']
        assert_operation_errors(
            data,
            [
                OperationMessage(
                    kind='VALIDATION',
                    message='Parent organization with ID 999999 not found.',
                )
            ],
        )
