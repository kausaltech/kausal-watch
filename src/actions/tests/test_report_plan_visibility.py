"""
Tests for the deploy check that compares what every hostname serves before and after.

The check has to distinguish two things a plain diff cannot: the change the migration is
supposed to make — an unlaunched production domain going dark — from any other change, which
means either a customer's site went down or a plan that was dark became readable.
"""

from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.utils import timezone

import pytest

from aplans.utils import RestrictedVisibilityModel

from actions.models.plan import PlanDomain, PublicationStatus

pytestmark = pytest.mark.django_db

INTERNAL = RestrictedVisibilityModel.VisibilityState.INTERNAL
PUBLIC = RestrictedVisibilityModel.VisibilityState.PUBLIC


def _full_report() -> dict[str, list[dict]]:
    out = StringIO()
    call_command('report_plan_visibility', stdout=out)
    return json.loads(out.getvalue())


def _report() -> dict[str, dict]:
    return {row['key']: row for row in _full_report()['surfaces']}


def _plan_report() -> dict[str, dict]:
    return {row['plan']: row for row in _full_report()['plans']}


def _baseline(tmp_path, rows, plans=None):
    """
    Write a baseline file.

    `plans` maps each plan identifier to whether it was readable anonymously. Left out, it records
    every plan as it is now, for the tests that are about hostnames only.
    """
    if plans is None:
        plans = {identifier: row['readable_anonymously'] for identifier, row in _plan_report().items()}
    path = tmp_path / 'baseline.json'
    plan_rows = [{'plan': identifier, 'readable_anonymously': readable} for identifier, readable in plans.items()]
    path.write_text(json.dumps({'surfaces': rows, 'plans': plan_rows}))
    return str(path)


def _row(key, *, served, launched, plan=None):
    row = {'key': key, 'served_anonymously': served, 'launched': launched}
    if plan is not None:
        row['plan'] = plan
    return row


def _verify(baseline_path, **options) -> str:
    out = StringIO()
    call_command('report_plan_visibility', verify=baseline_path, stdout=out, **options)
    return out.getvalue()


class TestReport:
    def test_it_reports_what_each_surface_serves(self, plan_factory, plan_domain_factory):
        live = plan_domain_factory(plan=plan_factory(visibility=PUBLIC, published_at=timezone.now() - timedelta(minutes=5)))
        dark = plan_domain_factory(plan=plan_factory(visibility=PUBLIC, published_at=None))

        report = _report()

        assert report[live.hostname]['availability'] == 'available'
        assert report[dark.hostname]['availability'] == 'unavailable'

    def test_it_skips_inactive_plans(self, plan_factory, plan_domain_factory):
        inactive = plan_domain_factory(plan=plan_factory(visibility=PUBLIC, is_active=False))
        assert inactive.hostname not in _report()

    def test_one_hostname_serving_two_plans_stays_two_surfaces(self, plan_factory, plan_domain_factory):
        hostname = 'shared.example.org'
        plan_domain_factory(plan=plan_factory(visibility=PUBLIC), hostname=hostname, base_path='/one')
        plan_domain_factory(plan=plan_factory(visibility=PUBLIC), hostname=hostname, base_path='/two')

        report = _report()

        assert f'{hostname}/one' in report
        assert f'{hostname}/two' in report


class TestPlanReport:
    """
    What each plan serves when no hostname is involved.

    `plan(id:)`, REST and search carry no hostname, and a wildcard host has no row of its own, so
    none of them appear among the surfaces. Each is gated by the plan's own answer, recorded here.
    """

    def test_it_reports_whether_each_plan_is_readable_anonymously(self, plan_factory):
        public = plan_factory(visibility=PUBLIC, published_at=None)
        internal = plan_factory(visibility=INTERNAL, published_at=timezone.now() - timedelta(minutes=5))

        plans = _plan_report()

        assert plans[public.identifier]['readable_anonymously'] is True
        assert plans[internal.identifier]['readable_anonymously'] is False

    def test_a_plan_with_no_domains_is_still_reported(self, plan_factory):
        """Such a plan is reachable only through its wildcard hosts and its identifier."""
        plan = plan_factory(visibility=PUBLIC)
        assert plan.identifier in _plan_report()

    def test_it_skips_inactive_plans(self, plan_factory):
        plan = plan_factory(visibility=PUBLIC, is_active=False)
        assert plan.identifier not in _plan_report()

    @pytest.mark.parametrize('visibility', [PUBLIC, INTERNAL])
    @pytest.mark.parametrize('launched', [True, False])
    def test_it_is_also_the_answer_on_every_wildcard_host(
        self, graphql_client_query_data, plan_factory, settings, visibility, launched
    ):
        """
        The plan's row stands in for its wildcard hosts, which the report cannot enumerate.

        Pinned here because the deploy check relies on it: a wildcard host is a preview surface,
        always launched, so it serves the site exactly when the plan is readable anonymously.
        """
        settings.HOSTNAME_PLAN_DOMAINS = ['dummy.io']
        plan = plan_factory(visibility=visibility, published_at=timezone.now() - timedelta(minutes=5) if launched else None)
        readable = _plan_report()[plan.identifier]['readable_anonymously']

        data = graphql_client_query_data(
            'query($hostname: String) { plansForHostname(hostname: $hostname) { domain { availability } } }',
            variables={'hostname': f'{plan.identifier}.dummy.io'},
        )

        assert (data['plansForHostname'][0]['domain']['availability'] == 'AVAILABLE') is readable


class TestVerify:
    def test_it_passes_when_nothing_changed(self, tmp_path, plan_factory, plan_domain_factory):
        domain = plan_domain_factory(plan=plan_factory(visibility=PUBLIC, published_at=timezone.now() - timedelta(minutes=5)))
        baseline = _baseline(tmp_path, [_row(domain.hostname, served=True, launched=True)])

        assert 'No unexplained changes' in _verify(baseline)

    def test_an_unlaunched_production_site_going_dark_is_the_intended_change(
        self,
        tmp_path,
        plan_factory,
        plan_domain_factory,
    ):
        """The exposure being fixed: it served the site while its plan had never been published."""
        domain = plan_domain_factory(plan=plan_factory(visibility=PUBLIC, published_at=None))
        baseline = _baseline(tmp_path, [_row(domain.hostname, served=True, launched=False)])

        output = _verify(baseline)

        assert 'as intended' in output
        assert domain.hostname in output

    def test_a_launched_site_going_dark_fails_as_an_outage(self, tmp_path, plan_factory, plan_domain_factory):
        domain = plan_domain_factory(plan=plan_factory(visibility=INTERNAL, published_at=None))
        baseline = _baseline(tmp_path, [_row(domain.hostname, served=True, launched=True)])

        with pytest.raises(CommandError):
            _verify(baseline)

    def test_a_dark_site_becoming_public_fails_as_an_exposure(self, tmp_path, plan_factory, plan_domain_factory):
        domain = plan_domain_factory(plan=plan_factory(visibility=PUBLIC, published_at=timezone.now() - timedelta(minutes=5)))
        baseline = _baseline(tmp_path, [_row(domain.hostname, served=False, launched=True)])

        with pytest.raises(CommandError):
            _verify(baseline)

    def test_a_preview_surface_going_dark_is_never_the_intended_change(
        self,
        tmp_path,
        plan_factory,
        plan_domain_factory,
    ):
        """
        The fix darkens production hostnames, never previews.

        A preview surface is always launched, so it only goes dark when the plan itself stopped
        being readable — an outage on a host somebody was using to look at the plan. The baseline
        says the plan had not launched, which is the shape of the intended change, so this is
        exactly the case that would slip through unnoticed.
        """
        plan = plan_factory(visibility=INTERNAL, published_at=None)
        domain = plan_domain_factory(plan=plan, deployment_environment=PlanDomain.DeploymentEnvironment.PREVIEW)
        baseline = _baseline(tmp_path, [_row(domain.hostname, served=True, launched=False)])

        with pytest.raises(CommandError):
            _verify(baseline)

    def test_a_site_launched_by_its_override_going_dark_fails_as_an_outage(
        self,
        tmp_path,
        plan_factory,
        plan_domain_factory,
    ):
        """
        A hostname forced to published is launched, whatever the plan's own date says.

        Such a site going dark is not the intended change, which only darkens hostnames that have
        not launched. The baseline cannot be trusted to say so: the plan never launched, and a
        baseline that records the plan's launch rather than the hostname's looks exactly like the
        intended change.
        """
        plan = plan_factory(visibility=INTERNAL, published_at=None)
        domain = plan_domain_factory(plan=plan, publication_status_override=PublicationStatus.PUBLISHED)
        baseline = _baseline(tmp_path, [_row(domain.hostname, served=True, launched=False)])

        with pytest.raises(CommandError):
            _verify(baseline)

    def test_a_surface_disappearing_fails(self, tmp_path):
        """A hostname in the baseline with no row now means the deploy lost a domain."""
        baseline = _baseline(tmp_path, [_row('vanished.example.org', served=True, launched=True)])

        with pytest.raises(CommandError):
            _verify(baseline)

    def test_a_new_surface_serving_the_site_fails_as_an_exposure(self, tmp_path, plan_factory, plan_domain_factory):
        """Nothing in the migration adds a hostname, so one that appeared and serves the plan is unexplained."""
        domain = plan_domain_factory(plan=plan_factory(visibility=PUBLIC, published_at=timezone.now() - timedelta(minutes=5)))
        baseline = _baseline(tmp_path, [])

        with pytest.raises(CommandError):
            _verify(baseline)
        assert domain.hostname in _report()

    def test_a_new_surface_that_serves_nothing_is_only_reported(self, tmp_path, plan_factory, plan_domain_factory):
        domain = plan_domain_factory(plan=plan_factory(visibility=INTERNAL, published_at=None))
        baseline = _baseline(tmp_path, [])

        output = _verify(baseline)

        assert domain.hostname in output
        assert 'No unexplained changes' in output

    def test_a_new_surface_can_be_explicitly_allowed(self, tmp_path, plan_factory, plan_domain_factory):
        """A hostname added on purpose between baseline and verification must not block the deploy."""
        domain = plan_domain_factory(plan=plan_factory(visibility=PUBLIC, published_at=timezone.now() - timedelta(minutes=5)))
        baseline = _baseline(tmp_path, [])

        output = _verify(baseline, allow_new=[domain.hostname])

        assert 'No unexplained changes' in output

    def test_a_plan_becoming_readable_anonymously_fails_as_an_exposure(self, tmp_path, plan_factory, plan_domain_factory):
        """
        The widening no hostname row shows.

        The plan's one domain was forced published, so that hostname reads the same before and
        after. What changed is everything without a row of its own: its wildcard hosts and its
        identifier now answer anyone.
        """
        plan = plan_factory(visibility=PUBLIC, published_at=None)
        domain = plan_domain_factory(plan=plan, publication_status_override=PublicationStatus.PUBLISHED)
        baseline = _baseline(
            tmp_path,
            [_row(domain.hostname, served=True, launched=True, plan=plan.identifier)],
            plans={plan.identifier: False},
        )

        assert f'EXPOSURE  plan {plan.identifier}' in self._verify_output(baseline)

    def test_a_plan_no_longer_readable_anonymously_fails_as_an_outage(self, tmp_path, plan_factory):
        plan = plan_factory(visibility=INTERNAL, published_at=None)
        baseline = _baseline(tmp_path, [], plans={plan.identifier: True})

        assert 'OUTAGE  plan' in self._verify_output(baseline)

    def test_a_plan_missing_from_the_baseline_that_is_readable_fails(self, tmp_path, plan_factory):
        plan_factory(visibility=PUBLIC)
        baseline = _baseline(tmp_path, [], plans={})

        with pytest.raises(CommandError):
            _verify(baseline)

    def test_a_plan_added_since_the_baseline_can_be_explicitly_allowed(self, tmp_path, plan_factory):
        plan = plan_factory(visibility=PUBLIC)
        baseline = _baseline(tmp_path, [], plans={})

        assert 'No unexplained changes' in _verify(baseline, allow_new=[f'plan {plan.identifier}'])

    def test_a_plan_in_the_baseline_that_is_gone_fails(self, tmp_path):
        baseline = _baseline(tmp_path, [], plans={'vanished': False})

        with pytest.raises(CommandError):
            _verify(baseline)

    def test_an_overridden_hostname_of_an_unreadable_plan_going_dark_is_expected(
        self, tmp_path, plan_factory, plan_domain_factory
    ):
        """
        The override made the hostname lookup look published, and nothing more.

        Everything the site loads goes through the plan's own gate, so a plan nobody could read
        anonymously never rendered there either. Its hostname asking for sign-in now takes nothing
        away from anyone.
        """
        plan = plan_factory(visibility=INTERNAL, published_at=None)
        domain = plan_domain_factory(plan=plan, publication_status_override=PublicationStatus.PUBLISHED)
        baseline = _baseline(
            tmp_path,
            [_row(domain.hostname, served=True, launched=True, plan=plan.identifier)],
            plans={plan.identifier: False},
        )

        output = _verify(baseline)

        assert 'as intended' in output
        assert domain.hostname in output

    def test_a_baseline_without_plans_is_refused(self, tmp_path):
        """An older capture covers hostnames only, and would pass without checking the rest."""
        path = tmp_path / 'baseline.json'
        path.write_text(json.dumps({'surfaces': []}))

        with pytest.raises(CommandError, match='Could not read the baseline'):
            _verify(str(path))

    @staticmethod
    def _verify_output(baseline_path) -> str:
        out = StringIO()
        with pytest.raises(CommandError):
            call_command('report_plan_visibility', verify=baseline_path, stdout=out)
        return out.getvalue()

    def test_an_unreadable_baseline_is_reported_clearly(self, tmp_path):
        with pytest.raises(CommandError, match='Could not read the baseline'):
            _verify(str(tmp_path / 'nope.json'))
