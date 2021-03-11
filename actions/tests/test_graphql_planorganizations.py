import pytest
from pytest_factoryboy import LazyFixture


@pytest.fixture
def suborganization(organization_factory, organization):
    return organization_factory(parent=organization)


@pytest.fixture
def another_organization(organization_factory):
    return organization_factory()


@pytest.mark.django_db
@pytest.mark.parametrize('with_ancestors', [True, False])
@pytest.mark.parametrize('organization__parent', [LazyFixture('another_organization')])
def test_planorganizations(graphql_client_query_data, another_organization, organization, suborganization, plan,
                           action_responsible_party, with_ancestors):
    superorganization = another_organization
    assert plan.organization == organization
    assert organization.parent == another_organization
    assert list(organization.children.all()) == [suborganization]
    assert organization.classification is None
    assert suborganization.classification is None
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $withAncestors: Boolean!) {
          planOrganizations(plan: $plan, withAncestors: $withAncestors) {
            id
            abbreviation
            name
            classification {
              name
            }
            parent {
              id
            }
          }
        }
        ''',
        variables={
            'plan': plan.identifier,
            'withAncestors': with_ancestors,
        }
    )
    expected_organizations = []
    if with_ancestors:
        expected_organizations.append({
            'id': str(superorganization.id),
            'abbreviation': superorganization.abbreviation,
            'name': superorganization.name,
            'classification': None,
            'parent': None,
        })
    expected_organizations.append({
        'id': str(organization.id),
        'abbreviation': organization.abbreviation,
        'name': organization.name,
        'classification': None,
        'parent': {
            'id': superorganization.id,
        },
    })
    expected = {
        'planOrganizations': expected_organizations
    }
    assert data == expected
