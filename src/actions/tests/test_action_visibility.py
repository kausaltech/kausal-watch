from __future__ import annotations

import json

import pytest

from aplans.utils import RestrictedVisibilityModel

from actions.models.action import Action
from actions.tests.factories import ActionFactory, PlanFactory

pytestmark = pytest.mark.django_db

PLAN_ACTIONS_QUERY = """
query planActions($plan: ID!) {
  planActions(plan: $plan) {
    identifier
  }
}
"""


def public_and_internal_actions(plan) -> tuple[Action, Action]:
    public = ActionFactory.create(plan=plan, visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
    internal = ActionFactory.create(plan=plan, visibility=RestrictedVisibilityModel.VisibilityState.INTERNAL)
    return public, internal


def visible_identifiers(user, plan=None) -> set[str]:
    qs = Action.objects.get_queryset().visible_for_user(user, plan)
    return set(qs.values_list('identifier', flat=True))


class TestInternalActionsAreForPlanStaffOnly:
    """
    Actions whose visibility is "internal" are shown only to the staff of their own plan.

    Plan staff means anyone with admin access to that plan: a general admin, a contact
    person for one of its actions or indicators, an organization admin, or a superuser.
    Being merely authenticated is not enough, and staff of one plan get no additional
    access to any other plan.
    """

    def test_anonymous_user_sees_only_public_actions(self, plan):
        public, _internal = public_and_internal_actions(plan)

        assert visible_identifiers(None) == {public.identifier}

    def test_authenticated_user_without_a_role_sees_only_public_actions(self, plan, user, person):
        public, _internal = public_and_internal_actions(plan)

        assert visible_identifiers(user) == {public.identifier}

    def test_general_admin_sees_internal_actions_of_their_plan(self, plan, plan_admin_user):
        public, internal = public_and_internal_actions(plan)

        assert visible_identifiers(plan_admin_user) == {public.identifier, internal.identifier}

    def test_contact_person_sees_internal_actions_of_their_plan(self, plan, person_factory):
        public, internal = public_and_internal_actions(plan)
        contact_person = person_factory(contact_for_actions=[public])

        assert visible_identifiers(contact_person.user) == {public.identifier, internal.identifier}

    def test_superuser_sees_internal_actions(self, plan, superuser):
        public, internal = public_and_internal_actions(plan)

        assert visible_identifiers(superuser) == {public.identifier, internal.identifier}

    def test_staff_of_one_plan_sees_only_public_actions_of_another(self, plan, plan_admin_user):
        other_plan = PlanFactory.create()
        public, _internal = public_and_internal_actions(other_plan)

        assert visible_identifiers(plan_admin_user, other_plan) == {public.identifier}

    def test_staff_access_does_not_leak_between_plans_when_unscoped(self, plan, plan_admin_user):
        own_public, own_internal = public_and_internal_actions(plan)
        other_plan = PlanFactory.create()
        other_public, _other_internal = public_and_internal_actions(other_plan)

        assert visible_identifiers(plan_admin_user) == {
            own_public.identifier,
            own_internal.identifier,
            other_public.identifier,
        }


class TestPlanActionsQueryVisibility:
    """The same rule must hold at the GraphQL endpoint, which is how the public UI reads actions."""

    def _query(self, graphql_client_query, plan) -> set[str]:
        response = graphql_client_query(PLAN_ACTIONS_QUERY, variables={'plan': plan.identifier})
        assert 'errors' not in response, json.dumps(response)
        return {action['identifier'] for action in response['data']['planActions']}

    def test_anonymous_user_sees_only_public_actions(self, plan, graphql_client_query):
        public, _internal = public_and_internal_actions(plan)

        assert self._query(graphql_client_query, plan) == {public.identifier}

    def test_authenticated_user_without_a_role_sees_only_public_actions(self, plan, client, user, person, graphql_client_query):
        public, _internal = public_and_internal_actions(plan)
        client.force_login(user)

        assert self._query(graphql_client_query, plan) == {public.identifier}

    def test_plan_staff_see_internal_actions(self, plan, client, plan_admin_user, graphql_client_query):
        public, internal = public_and_internal_actions(plan)
        client.force_login(plan_admin_user)

        assert self._query(graphql_client_query, plan) == {public.identifier, internal.identifier}
