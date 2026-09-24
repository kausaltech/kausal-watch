"""
Tests for Plan.visibility, the single gate on who may read a plan.

`visibility` decides whether a caller may read the plan at all, everywhere: GraphQL by hostname
or identifier, REST, search and exports. It is independent of `published_at`, which says only
whether the production surface has been switched on — hence the `launched` column below, which
must never change the answer.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

import pytest

from kausal_common.testing.utils import parse_table

from aplans.utils import RestrictedVisibilityModel

from actions.models import Plan

pytestmark = pytest.mark.django_db

INTERNAL = RestrictedVisibilityModel.VisibilityState.INTERNAL
PUBLIC = RestrictedVisibilityModel.VisibilityState.PUBLIC

# `user` is resolved by _user_for(): a signed-in user with access to this plan, a signed-in user
# whose access is to some other plan, or nobody signed in at all.
VISIBILITY_MATRIX = """
    visibility  launched  user            can_read
    public      +         anonymous       +
    public      -         anonymous       +        # the state the production-domain leak lived in
    public      -         other_plan      +
    public      +         with_access     +
    internal    +         anonymous       -        # launching never widens access
    internal    -         anonymous       -
    internal    +         other_plan      -
    internal    -         other_plan      -
    internal    +         with_access     +
    internal    -         with_access     +
"""


def _user_for(kind: str, plan: Plan, person_factory, plan_factory):
    if kind == 'anonymous':
        return AnonymousUser()
    if kind == 'with_access':
        return person_factory(general_admin_plans=[plan]).user
    return person_factory(general_admin_plans=[plan_factory()]).user


def _make_plan(plan_factory, visibility: str, launched: bool) -> Plan:
    return plan_factory(
        visibility=visibility,
        published_at=timezone.now() - timedelta(minutes=5) if launched else None,
    )


@pytest.mark.parametrize(*parse_table(VISIBILITY_MATRIX))
def test_visibility_alone_decides_who_may_read_a_plan(
    plan_factory,
    person_factory,
    visibility,
    launched,
    user,
    can_read,
):
    plan = _make_plan(plan_factory, visibility, launched)
    assert plan.is_visible_for_user(_user_for(user, plan, person_factory, plan_factory)) is can_read


@pytest.mark.parametrize(*parse_table(VISIBILITY_MATRIX))
def test_the_queryset_filter_agrees_with_the_instance_check(
    plan_factory,
    person_factory,
    visibility,
    launched,
    user,
    can_read,
):
    """
    The two derivations in PlanPermissionPolicy must never disagree.

    `construct_perm_q*` and `*_has_perm` are separate implementations of the same rule, and two
    derivations of visibility drifting apart is exactly what this model exists to prevent.
    """
    plan = _make_plan(plan_factory, visibility, launched)
    user_obj = _user_for(user, plan, person_factory, plan_factory)
    assert Plan.objects.qs.visible_for_user(user_obj).filter(pk=plan.pk).exists() is can_read


def test_inactive_plan_stays_hidden_even_when_public(plan_factory):
    plan = plan_factory(visibility=PUBLIC, is_active=False)
    assert plan.is_visible_for_user(AnonymousUser()) is False


def test_new_plans_are_internal_by_default():
    assert Plan().visibility == INTERNAL


class TestRestApiFollowsVisibility:
    """
    The REST plan endpoint must use the same gate.

    It previously derived its own answer as `live() | adminable`, which was equivalent only while
    a launched plan was necessarily public. It would otherwise have served an internal plan that
    has launched to anonymous callers.
    """

    @pytest.mark.parametrize(
        *parse_table("""
        visibility  launched  listed
        public      -         +
        public      +         +
        internal    +         -
        internal    -         -
    """)
    )
    def test_anonymous_plan_list_follows_visibility(
        self,
        api_client,
        plan_list_url,
        plan_factory,
        visibility,
        launched,
        listed,
    ):
        plan = _make_plan(plan_factory, visibility, launched)
        identifiers = [row['identifier'] for row in api_client.get(plan_list_url).json_data['results']]
        assert (plan.identifier in identifiers) is listed


def _nested_urls(plan: Plan) -> dict[str, str]:
    from django.urls import reverse

    from actions.tests.factories import ActionImplementationPhaseFactory, ActionScheduleFactory
    from indicators.tests.factories import IndicatorFactory

    ActionScheduleFactory.create(plan=plan)
    ActionImplementationPhaseFactory.create(plan=plan)
    indicator = IndicatorFactory.create(organization=plan.organization, plans=[plan])
    detail = {'plan_pk': plan.pk, 'pk': indicator.pk}
    return {
        'action_schedules': reverse('action_schedule-list', args=(plan.pk,)),
        'action_implementation_phases': reverse('action_implementation_phase-list', args=(plan.pk,)),
        'indicators': reverse('indicator-list', args=(plan.pk,)),
        'indicator': reverse('indicator-detail', kwargs=detail),
        'indicator_values': reverse('indicator-values', kwargs=detail),
        'indicator_goals': reverse('indicator-goals', kwargs=detail),
        'indicator_dimensions': reverse('indicator-dimensions', kwargs=detail),
        'actions': reverse('action-list', args=(plan.pk,)),
        'category_types': reverse('category-type-list', args=(plan.pk,)),
        'action_tasks': reverse('action-task-list', args=(plan.pk,)),
    }


NESTED_ENDPOINTS = [
    'action_schedules',
    'action_implementation_phases',
    'indicators',
    'indicator',
    'indicator_values',
    'indicator_goals',
    'indicator_dimensions',
    'actions',
    'category_types',
    'action_tasks',
]


class TestNestedRestEndpointsFollowVisibility:
    """
    Every endpoint nested under a plan must gate on that plan's visibility.

    A nested router does not run `PlanViewSet.get_queryset` for the parent, so each viewset has
    to look its plan up through the gate itself. One that fetches the plan directly serves an
    internal plan's data to anyone.
    """

    @pytest.mark.parametrize('endpoint', NESTED_ENDPOINTS)
    def test_internal_plan_is_not_found_anonymously(self, api_client, plan_factory, endpoint):
        plan = _make_plan(plan_factory, INTERNAL, launched=True)
        url = _nested_urls(plan)[endpoint]
        assert api_client.get(url).status_code == 404

    @pytest.mark.parametrize('endpoint', NESTED_ENDPOINTS)
    def test_public_plan_is_served_anonymously(self, api_client, plan_factory, endpoint):
        plan = _make_plan(plan_factory, PUBLIC, launched=True)
        url = _nested_urls(plan)[endpoint]
        assert api_client.get(url).status_code == 200
