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

from actions.models.plan import PlanDomain

pytestmark = pytest.mark.django_db

INTERNAL = RestrictedVisibilityModel.VisibilityState.INTERNAL
PUBLIC = RestrictedVisibilityModel.VisibilityState.PUBLIC


def _report() -> dict[str, dict]:
    out = StringIO()
    call_command('report_plan_visibility', stdout=out)
    return {row['key']: row for row in json.loads(out.getvalue())['surfaces']}


def _baseline(tmp_path, rows):
    path = tmp_path / 'baseline.json'
    path.write_text(json.dumps({'surfaces': rows}))
    return str(path)


def _row(key, *, served, launched):
    return {'key': key, 'served_anonymously': served, 'launched': launched}


def _verify(baseline_path, **options) -> str:
    out = StringIO()
    call_command('report_plan_visibility', verify=baseline_path, stdout=out, **options)
    return out.getvalue()


class TestReport:
    def test_it_reports_what_each_surface_serves(self, plan_factory, plan_domain_factory):
        live = plan_domain_factory(plan=plan_factory(visibility=PUBLIC, published_at=timezone.now() - timedelta(minutes=5)))
        dark = plan_domain_factory(plan=plan_factory(visibility=PUBLIC, published_at=None))

        report = _report()

        assert report[live.hostname]['status'] == 'available'
        assert report[dark.hostname]['status'] == 'unavailable'

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

    def test_an_unreadable_baseline_is_reported_clearly(self, tmp_path):
        with pytest.raises(CommandError, match='Could not read the baseline'):
            _verify(str(tmp_path / 'nope.json'))
