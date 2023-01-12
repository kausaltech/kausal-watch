from datetime import timedelta

from django.utils import timezone
import pytest

from actions.models.plan import PublicationStatus

pytestmark = pytest.mark.django_db


GET_PLANS_BY_HOSTNAME_QUERY = '''
  query GetPlansByHostname($hostname: String) {
    plansForHostname(hostname: $hostname) {
      ... on Plan {
        identifier
        id
      }
      domains {
        hostname
        basePath
        status
      }
      primaryLanguage
      publishedAt
    }
  }
'''

GET_PLANS_BY_HOSTNAME_QUERY_STATUSMESSAGE = '''
  query GetPlansByHostname($hostname: String) {
    plansForHostname(hostname: $hostname) {
      domains {
        status
        statusMessage
      }
    }
  }
'''


@pytest.mark.parametrize(
    "publication_status_override,delta_minutes,publication_status",
    [(None, -5, PublicationStatus.PUBLISHED),
     (None, 5, PublicationStatus.SCHEDULED),
     (None, None, PublicationStatus.UNPUBLISHED),
     (PublicationStatus.UNPUBLISHED, -5, PublicationStatus.UNPUBLISHED),
     (PublicationStatus.PUBLISHED, 5, PublicationStatus.PUBLISHED),
     (PublicationStatus.PUBLISHED, None, PublicationStatus.PUBLISHED)]
)
def test_get_plans_by_hostname(graphql_client_query_data,
                               plan_factory,
                               plan_domain_factory,
                               publication_status_override,
                               delta_minutes,
                               publication_status):
    published_at = None
    if delta_minutes is not None:
        published_at = timezone.now() + timedelta(minutes=delta_minutes)
    plan = plan_factory(published_at=published_at)
    domain = plan_domain_factory(plan=plan, publication_status_override=publication_status_override)
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY,
        variables={'hostname': domain.hostname}
    )
    plans = data['plansForHostname']
    expected = [
        {
            'domains': [{
                'basePath': domain.base_path,
                'hostname': domain.hostname,
                'status': publication_status.name,
            }],
            'primaryLanguage': plan.primary_language,
            'publishedAt': published_at.isoformat() if published_at else None
        }
    ]
    if publication_status == PublicationStatus.PUBLISHED:
        expected[0]['identifier'] = plan.identifier
        expected[0]['id'] = plan.identifier
    assert plans == expected


@pytest.mark.parametrize(
    "publication_status_override,has_message",
    [(PublicationStatus.UNPUBLISHED, True),
     (PublicationStatus.PUBLISHED, False)]
)
def test_get_correct_domain_by_hostname(graphql_client_query_data,
                                        plan_factory,
                                        plan_domain_factory,
                                        publication_status_override,
                                        has_message):

    plan = plan_factory()
    domain = plan_domain_factory(plan=plan, publication_status_override=publication_status_override)
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY_STATUSMESSAGE,
        variables={'hostname': domain.hostname}
    )
    plans = data['plansForHostname']
    message = plans[0]['domains'][0]['statusMessage']
    if has_message:
        assert message is not None
    else:
        assert message is None


DUMMY_DOMAIN = 'dummy.io'


@pytest.fixture
def use_dummy_plan_hostname(settings):
    settings.HOSTNAME_PLAN_DOMAINS = [DUMMY_DOMAIN]


def test_plans_for_hostname_without_domains(graphql_client_query_data,
                                            use_dummy_plan_hostname,
                                            plan):
    data = graphql_client_query_data(
        GET_PLANS_BY_HOSTNAME_QUERY,
        variables={'hostname': f'{plan.identifier}.{DUMMY_DOMAIN}'}
    )
    planData = data['plansForHostname'][0]
    assert len(planData['domains']) == 0
    assert planData['identifier'] == plan.identifier
