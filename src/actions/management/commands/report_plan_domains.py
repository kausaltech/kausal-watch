"""
Report which domain each plan's links use, and where more than one could be.

A plan's domains are ordered, and links use the first one the selection rules allow (see
`Plan.find_canonical_domain()`). The first row is not always that one: a preview domain listed
above a production one, or a production domain that has not launched, is passed over. The
report lists every plan's domains in order and marks the one in use, so that is visible.

A plan with more than one launched production domain is flagged. The order settles which one
is used, but an alias that should redirect usually belongs in `redirect_to_hostname` instead.

    python manage.py report_plan_domains [--multiple-only] [--include-inactive]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.management.base import BaseCommand

from actions.models.plan import Plan

if TYPE_CHECKING:
    from argparse import ArgumentParser

    from actions.models.plan import PlanDomain


def _competing_production_domains(domains: list[PlanDomain]) -> list[PlanDomain]:
    """Return the launched, non-redirect production domains, which compete for the canonical place."""
    return [d for d in domains if not d.redirect_to_hostname and not d.is_preview_surface and d.is_launched]


def _describe_domain(domain: PlanDomain, in_use: bool) -> str:
    marker = '*' if in_use else ' '
    hostpath = domain.hostname + (domain.base_path or '')
    environment = domain.deployment_environment or 'production (unset)'
    if domain.redirect_to_hostname:
        status = f'redirects to {domain.redirect_to_hostname}'
    else:
        status = 'launched' if domain.is_launched else 'not launched'
    return f'  {marker} {hostpath:<40} {environment:<20} {status}'


class Command(BaseCommand):
    help = "Report which domain each plan's links use, and flag plans with competing production domains."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            '--multiple-only',
            action='store_true',
            help='List only the plans with more than one launched production domain.',
        )
        parser.add_argument(
            '--include-inactive',
            action='store_true',
            help='Include plans marked inactive, which are never served.',
        )

    def handle(self, *args: Any, **options: Any) -> None:
        plans = Plan.objects.get_queryset().prefetch_related('domains').order_by('identifier')
        if not options['include_inactive']:
            plans = plans.filter(is_active=True)

        sections = []
        flagged = 0
        for plan in plans:
            domains = plan.ordered_domains()
            competing = _competing_production_domains(domains)
            if len(competing) > 1:
                flagged += 1
            elif options['multiple_only']:
                continue
            sections.append(self._describe_plan(plan, domains, competing))

        self.stdout.write('\n\n'.join(sections))
        self.stdout.write(f'\n\n{len(sections)} plans listed, {flagged} with competing production domains.')

    def _describe_plan(self, plan: Plan, domains: list[PlanDomain], competing: list[PlanDomain]) -> str:
        state = 'live' if plan.is_live() else 'not live'
        in_use = plan.find_canonical_domain()
        try:
            url = plan.view_url_for_domain(in_use)
        except ValueError as e:
            url = f'ERROR: {e}'
        lines = [f'{plan.identifier} ({state}): {url}']
        lines.extend(_describe_domain(domain, in_use is not None and domain.pk == in_use.pk) for domain in domains)
        if in_use is None:
            lines.append('  (no domain in use: links use the wildcard hostname)')
        if len(competing) > 1:
            lines.append(f'  ! {len(competing)} production domains compete; the first one listed is used')
        return '\n'.join(lines)
