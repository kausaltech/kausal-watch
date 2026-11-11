"""Marking actions as complete for a report from the action admin."""

from __future__ import annotations

import pytest

from actions.tests import action_admin_helpers as h
from actions.tests.factories import ActionFactory, PlanFactory
from reports.tests.factories import ReportFactory

pytestmark = pytest.mark.django_db

ADMIN_BUTTONS_QUERY = """
  query ($plan: ID!) {
    planActions(plan: $plan) {
      id
      adminButtons {
        url
        label
      }
    }
  }
"""


@pytest.fixture
def plan():
    return PlanFactory.create()


@pytest.fixture
def action(plan):
    return ActionFactory.create(plan=plan)


@pytest.fixture
def report(plan):
    return ReportFactory.create(type__plan=plan)


def button_urls(graphql_client_query_data, client, user, action) -> list[str]:
    client.force_login(user)
    data = graphql_client_query_data(ADMIN_BUTTONS_QUERY, variables={'plan': action.plan.identifier})
    [buttons] = [a['adminButtons'] for a in data['planActions'] if a['id'] == str(action.pk)]
    return [button['url'] for button in buttons]


@pytest.mark.parametrize('make_user', [h.plan_admin_for, h.make_contact_person])
def test_mark_and_undo(client, action, report, make_user):
    client.force_login(make_user(action))

    assert client.get(h.mark_as_complete_url(action, report.pk)).status_code == 200
    response = client.post(h.mark_as_complete_url(action, report.pk))

    assert response.status_code == 302
    assert response['Location'] == h.index_url()
    assert action.is_complete_for_report(report)

    assert client.get(h.undo_marking_as_complete_url(action, report.pk)).status_code == 200
    client.post(h.undo_marking_as_complete_url(action, report.pk))

    assert not action.is_complete_for_report(report)


def test_contact_person_of_another_action_cannot_mark(client, action, report):
    client.force_login(h.make_contact_person(ActionFactory.create(plan=action.plan)))

    client.post(h.mark_as_complete_url(action, report.pk))

    assert not action.is_complete_for_report(report)


def test_report_of_another_plan_is_refused(client, action):
    other_report = ReportFactory.create()
    client.force_login(h.make_plan_admin(action.plan))

    client.post(h.mark_as_complete_url(action, other_report.pk))

    assert not action.is_complete_for_report(other_report)


def test_only_admins_can_mark_when_the_report_type_says_so(client, action, report):
    report.type.only_plan_admins_can_mark_actions_as_complete = True
    report.type.save()
    client.force_login(h.make_contact_person(action))

    client.post(h.mark_as_complete_url(action, report.pk))

    assert not action.is_complete_for_report(report)

    client.force_login(h.make_plan_admin(action.plan))
    client.post(h.mark_as_complete_url(action, report.pk))

    assert action.is_complete_for_report(report)


def test_listing_offers_the_button_that_applies(graphql_client_query_data, client, action, report):
    user = h.make_contact_person(action)

    assert h.mark_as_complete_url(action, report.pk) in button_urls(graphql_client_query_data, client, user, action)

    client.post(h.mark_as_complete_url(action, report.pk))
    urls = button_urls(graphql_client_query_data, client, user, action)

    assert h.undo_marking_as_complete_url(action, report.pk) in urls
    assert h.mark_as_complete_url(action, report.pk) not in urls


def test_listing_offers_no_button_for_an_action_the_user_cannot_edit(graphql_client_query_data, client, action, report):
    other_action = ActionFactory.create(plan=action.plan)
    user = h.make_contact_person(other_action)

    assert h.mark_as_complete_url(action, report.pk) not in button_urls(graphql_client_query_data, client, user, action)


def test_listing_offers_no_button_to_contact_persons_when_only_admins_can_mark(graphql_client_query_data, client, action, report):
    report.type.only_plan_admins_can_mark_actions_as_complete = True
    report.type.save()
    contact_person = h.make_contact_person(action)
    plan_admin = h.make_plan_admin(action.plan)
    url = h.mark_as_complete_url(action, report.pk)

    assert url not in button_urls(graphql_client_query_data, client, contact_person, action)
    assert url in button_urls(graphql_client_query_data, client, plan_admin, action)
