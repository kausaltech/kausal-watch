import pytest

from actions.tests.factories import ActionFactory, ActionResponsiblePartyFactory, OrganizationFactory, PlanFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def suborganization(organization_factory, organization):
    return organization_factory(parent=organization)


@pytest.fixture
def another_organization(organization_factory):
    return organization_factory()


@pytest.mark.parametrize('with_ancestors', [True, False])
def test_planorganizations(graphql_client_query_data, with_ancestors):
    superorganization = OrganizationFactory()
    organization = OrganizationFactory(parent=superorganization)
    suborganization = OrganizationFactory(parent=organization)
    plan = PlanFactory(organization=organization)
    assert organization.classification is None
    assert suborganization.classification is None
    action = ActionFactory(plan=plan)
    ActionResponsiblePartyFactory(action=action, organization=organization)
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
