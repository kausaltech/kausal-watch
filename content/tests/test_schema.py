from __future__ import annotations

import pytest

from content.models import SiteGeneralContent
from content.tests.factories import SiteGeneralContentFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('indicator_term', SiteGeneralContent.IndicatorTerm.values)
def test_indicator_term_in_general_content(graphql_client_query_data, indicator_term):
    sgc = SiteGeneralContentFactory.create(indicator_term=indicator_term)
    data = graphql_client_query_data(
        """
        query($plan: ID!) {
          plan(id: $plan) {
            generalContent {
              indicatorTerm
            }
          }
        }
        """,
        variables=dict(plan=sgc.plan.identifier),
    )
    expected = {
        'plan': {
            'generalContent': {
                'indicatorTerm': indicator_term.upper(),
            },
        },
    }
    assert data == expected
