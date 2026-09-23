"""
Report or verify what every hostname serves an anonymous visitor.

Written for the visibility migration, where the risk runs both ways: a plan that was dark
becoming publicly readable, or a live customer site going dark. Both are answers to the same
question — what does this hostname serve someone who is not signed in — so the check is to
record that answer for every hostname before the deploy and compare after.

The deploy deliberately changes some of them: an unlaunched production domain of a plan that
migrates to `public` stops serving the site, which is the fix. So a plain diff is not the test;
`--verify` takes the baseline, works out which surfaces are *expected* to change, and fails only
on the ones that are not.

    # before deploying, on the old revision (see the deploy plan for the snippet)
    python manage.py shell_plus --quiet-load -c '<capture snippet>' > baseline.json

    # after migrating
    python manage.py report_plan_visibility --verify baseline.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.contrib.auth.models import AnonymousUser
from django.core.management.base import BaseCommand, CommandError

from actions.models.plan import Plan, PlanDomainStatus
from actions.plan_visibility import all_surfaces

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from actions.plan_visibility import SurfaceReport

# A surface that served the site before and does not now is an outage; one that serves it now and
# did not before is an exposure. Only the first is expected, and only where the plan had not
# launched — that is precisely the bug being fixed.
EXPECTED_LOSS_REASON = 'production hostname of a plan that has not launched'


class Command(BaseCommand):
    help = 'Report what every plan hostname serves anonymously, or verify it against a baseline.'

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            '--verify',
            metavar='BASELINE',
            help='Compare against a baseline captured before the deploy, and fail on unexpected changes.',
        )
        parser.add_argument(
            '--include-inactive',
            action='store_true',
            help='Include plans marked inactive, which are never served.',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        plans = Plan.objects.get_queryset().prefetch_related('domains')
        if not options['include_inactive']:
            plans = plans.filter(is_active=True)

        # Anonymous is the viewer that matters: the question is what the public gets.
        surfaces = list(all_surfaces(plans, AnonymousUser()))

        if options['verify']:
            self._verify(surfaces, options['verify'])
            return

        json.dump(
            {'surfaces': [surface.as_dict() for surface in surfaces]},
            self.stdout,
            indent=2,
            sort_keys=True,
        )
        self.stdout.write('')

    def _verify(self, surfaces: list[SurfaceReport], baseline_path: str) -> None:
        try:
            with Path(baseline_path).open() as baseline_file:
                baseline = {row['key']: row for row in json.load(baseline_file)['surfaces']}
        except (OSError, KeyError, ValueError) as error:
            raise CommandError(f'Could not read the baseline {baseline_path}: {error}') from error

        current = {surface.key: surface for surface in surfaces}
        expected, unexpected, gone, appeared = [], [], [], []

        for key, before in baseline.items():
            after = current.get(key)
            if after is None:
                gone.append(key)
                continue
            served_before = before['served_anonymously']
            served_after = after.status == PlanDomainStatus.AVAILABLE
            if served_before == served_after:
                continue
            # Losing the site is expected exactly where the plan had not launched; gaining it is
            # never expected, because nothing in this change widens who may read a plan.
            if not served_after and not before['launched']:
                expected.append((key, EXPECTED_LOSS_REASON))
            else:
                unexpected.append((key, served_before, served_after))

        appeared = sorted(set(current) - set(baseline))

        self._report(len(baseline), expected, unexpected, gone, appeared)

        if unexpected or gone:
            raise CommandError('Visibility changed in ways the migration does not explain.')

    def _report(
        self,
        checked: int,
        expected: list[tuple[str, str]],
        unexpected: list[tuple[str, bool, bool]],
        gone: list[str],
        appeared: list[str],
    ) -> None:
        self.stdout.write(f'Checked {checked} surfaces against the baseline.')

        if expected:
            self.stdout.write(self.style.WARNING(f'\n{len(expected)} stopped serving the site, as intended:'))
            for key, reason in sorted(expected):
                self.stdout.write(f'  {key} — {reason}')

        if appeared:
            self.stdout.write(f'\n{len(appeared)} surfaces are new since the baseline:')
            for key in appeared:
                self.stdout.write(f'  {key}')

        if gone:
            self.stdout.write(self.style.ERROR(f'\n{len(gone)} surfaces in the baseline no longer exist:'))
            for key in sorted(gone):
                self.stdout.write(f'  {key}')

        if unexpected:
            self.stdout.write(self.style.ERROR(f'\n{len(unexpected)} changed unexpectedly:'))
            for key, before, after in sorted(unexpected):
                was = 'served the site' if before else 'was dark'
                now = 'serves the site' if after else 'is dark'
                marker = 'EXPOSURE' if after else 'OUTAGE'
                self.stdout.write(f'  {marker}  {key} — {was}, now {now}')
        elif not gone:
            self.stdout.write(self.style.SUCCESS('\nNo unexplained changes.'))
