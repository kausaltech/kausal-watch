"""
Tests for the plan-surface report.

`plan_surfaces()` answers "where is this plan served, and what does each hostname show", which
is the question the visibility model exists to answer. It backs the deploy check that compares
what every hostname served before and after the migration, and is shaped to be reusable — the
admin could show the same list on a plan's page.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.utils import timezone

import pytest

from kausal_common.testing.utils import parse_table

from aplans.utils import RestrictedVisibilityModel

from actions.models.plan import PlanDomain, PlanDomainAvailability
from actions.plan_visibility import plan_surfaces

pytestmark = pytest.mark.django_db

INTERNAL = RestrictedVisibilityModel.VisibilityState.INTERNAL
PUBLIC = RestrictedVisibilityModel.VisibilityState.PUBLIC

PRODUCTION = PlanDomain.DeploymentEnvironment.PRODUCTION
PREVIEW = PlanDomain.DeploymentEnvironment.PREVIEW


def _plan(plan_factory, visibility, *, launched):
    return plan_factory(
        visibility=visibility,
        published_at=timezone.now() - timedelta(minutes=5) if launched else None,
    )


class TestPlanSurfaces:
    @pytest.mark.parametrize(*parse_table("""
        environment  visibility  launched  availability
        production   public      +         AVAILABLE
        production   public      -         UNAVAILABLE
        production   internal    +         SIGN_IN_REQUIRED
        production   internal    -         UNAVAILABLE
        preview      public      -         AVAILABLE
        preview      internal    -         SIGN_IN_REQUIRED
    """))
    def test_it_reports_what_each_hostname_serves_anonymously(
        self, plan_factory, plan_domain_factory, environment, visibility, launched, availability,
    ):
        plan = _plan(plan_factory, visibility, launched=launched)
        environments = {'production': PRODUCTION, 'preview': PREVIEW}
        plan_domain_factory(plan=plan, deployment_environment=environments[environment])

        (surface,) = plan_surfaces(plan, AnonymousUser())

        assert surface.availability == PlanDomainAvailability(availability.lower())

    def test_it_reports_every_domain_of_a_plan(self, plan_factory, plan_domain_factory):
        plan = _plan(plan_factory, PUBLIC, launched=False)
        production = plan_domain_factory(plan=plan, deployment_environment=PRODUCTION)
        preview = plan_domain_factory(plan=plan, deployment_environment=PREVIEW)

        by_hostname = {s.hostname: s for s in plan_surfaces(plan, AnonymousUser())}

        assert by_hostname[production.hostname].availability == PlanDomainAvailability.UNAVAILABLE
        assert by_hostname[preview.hostname].availability == PlanDomainAvailability.AVAILABLE

    def test_it_answers_per_viewer(self, plan_factory, plan_domain_factory, person_factory):
        plan = _plan(plan_factory, INTERNAL, launched=True)
        plan_domain_factory(plan=plan, deployment_environment=PRODUCTION)
        person = person_factory(general_admin_plans=[plan])

        anonymous = plan_surfaces(plan, AnonymousUser())[0]
        privileged = plan_surfaces(plan, person.user)[0]

        assert anonymous.availability == PlanDomainAvailability.SIGN_IN_REQUIRED
        assert privileged.availability == PlanDomainAvailability.AVAILABLE

    def test_it_carries_the_base_path_so_multi_plan_hostnames_stay_distinct(
        self, plan_factory, plan_domain_factory,
    ):
        """One hostname can serve several plans, so a report keyed on hostname alone would collide."""
        hostname = 'shared.example.org'
        first = plan_domain_factory(plan=_plan(plan_factory, PUBLIC, launched=True), hostname=hostname, base_path='/one')
        second = plan_domain_factory(plan=_plan(plan_factory, PUBLIC, launched=True), hostname=hostname, base_path='/two')

        keys = {plan_surfaces(d.plan, AnonymousUser())[0].key for d in (first, second)}

        assert keys == {f'{hostname}/one', f'{hostname}/two'}

    def test_it_carries_the_visibility_so_a_consumer_can_tell_the_two_dark_states_apart(
        self, plan_factory, plan_domain_factory,
    ):
        """
        `UNAVAILABLE` does not imply the data is private.

        A public plan that has not launched is still readable by identifier, by design; an
        internal one is not. A check that conflated them would either miss a leak or chase one
        that was never there.
        """
        unlaunched = plan_domain_factory(plan=_plan(plan_factory, PUBLIC, launched=False))
        internal = plan_domain_factory(plan=_plan(plan_factory, INTERNAL, launched=False))

        surfaces = {
            d.hostname: plan_surfaces(d.plan, AnonymousUser())[0] for d in (unlaunched, internal)
        }

        assert surfaces[unlaunched.hostname].availability == PlanDomainAvailability.UNAVAILABLE
        assert surfaces[unlaunched.hostname].visibility == PUBLIC
        assert surfaces[internal.hostname].visibility == INTERNAL
