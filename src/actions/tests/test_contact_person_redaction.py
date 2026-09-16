"""
Contact-person redaction must survive the GraphQL node resolvers.

`Action.get_redacted_contact_persons()` replaces each row's person with a redacted copy, but the node's
`resolve_person()` then looks the person up in the plan cache — which holds the full record. Reading the
cache unconditionally undid the redaction, publishing fields the plan had configured away.
"""

from __future__ import annotations

import pytest

from actions.models.features import PlanFeatures
from actions.tests.factories import ActionContactFactory
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db

QUERY = """
    query($plan: ID!) {
      planActions(plan: $plan) { contactPersons { person { firstName email } } }
    }
"""


def _contacts(graphql_client_query_data, plan):
    data = graphql_client_query_data(QUERY, variables={'plan': plan.identifier})
    return [c for a in data['planActions'] for c in a['contactPersons']]


@pytest.fixture
def action_with_contact_person(action):
    person = PersonFactory.create(organization=action.plan.organization, email='secret@example.com')
    ActionContactFactory.create(action=action, person=person)
    return action, person


def _set_visibility(plan, value):
    plan.features.contact_persons_public_data = value
    plan.features.save()


def test_name_level_redaction_hides_the_email(graphql_client_query_data, action_with_contact_person):
    action, person = action_with_contact_person
    _set_visibility(action.plan, PlanFeatures.ContactPersonsPublicData.NAME)

    (contact,) = _contacts(graphql_client_query_data, action.plan)

    assert contact['person']['firstName'] == person.first_name
    assert not contact['person']['email']


def test_full_visibility_still_exposes_the_email(graphql_client_query_data, action_with_contact_person):
    action, person = action_with_contact_person
    _set_visibility(action.plan, PlanFeatures.ContactPersonsPublicData.ALL)

    (contact,) = _contacts(graphql_client_query_data, action.plan)

    assert contact['person']['email'] == person.email
