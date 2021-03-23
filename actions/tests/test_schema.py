import pytest

from actions.models import get_default_language
from actions.tests.factories import PlanFactory
from admin_site.tests.factories import AdminHostnameFactory, ClientPlanFactory


@pytest.mark.django_db
@pytest.mark.parametrize('show_admin_link', [True, False])
def test_plan_node(graphql_client_query_data, show_admin_link):
    plan = PlanFactory(show_admin_link=show_admin_link)
    admin_hostname = AdminHostnameFactory()
    client_plan = ClientPlanFactory(plan=plan, client=admin_hostname.client)
    data = graphql_client_query_data(
        '''
        query($plan: ID!, $hostname: String!) {
          plan(id: $plan) {
            __typename
            actions {
              __typename
            }
            adminUrl
            categoryTypes {
              __typename
            }
            domain(hostname: $hostname) {
              __typename
            }
            id
            image {
              __typename
            }
            impactGroups {
              __typename
            }
            lastActionIdentifier
            mainMenu {
              __typename
            }
            pages {
              __typename
            }
            primaryLanguage
            serveFileBaseUrl
            footer {
              __typename
            }
          }
        }
        ''',
        variables=dict(plan=plan.identifier, hostname=plan.domains.first().hostname)
    )
    if show_admin_link:
        expected_admin_url = client_plan.client.get_admin_url()
    else:
        expected_admin_url = None
    expected = {
        'plan': {
            '__typename': 'Plan',
            'actions': [{
                '__typename': 'Action',
            }],
            'adminUrl': expected_admin_url,
            'categoryTypes': [{
                '__typename': 'CategoryType',
            }],
            'domain': {
                '__typename': 'PlanDomain',
            },
            'id': plan.identifier,
            'image': {
                '__typename': 'Image',
            },
            'impactGroups': [{
                '__typename': 'ImpactGroup',
            }],
            'lastActionIdentifier': plan.get_last_action_identifier(),
            'mainMenu': {
                '__typename': 'MainMenu',
            },
            'pages': [{
                '__typename': 'PlanRootPage',
            }],
            'primaryLanguage': get_default_language(),
            'serveFileBaseUrl': 'http://testserver',
            'footer': {
                '__typename': 'Footer',
            },
        }
    }
    assert data == expected
