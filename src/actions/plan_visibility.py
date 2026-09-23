"""
Where a plan is served, and what each of its hostnames shows.

The visibility model splits one question in two — may this viewer read the plan, and has this
hostname launched — and `PlanDomain.status_for_user` folds them back into the single answer the
public UI needs. This module reports that answer for every hostname a plan has, which is what a
human needs in order to check a plan's exposure at a glance.

It exists as its own module rather than inside a management command because the same list is
what a plan's admin page would want to show: *this plan is served at these addresses, and this
is what a visitor gets at each*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from kausal_common.users import UserOrAnon

    from actions.models.plan import Plan, PlanDomain, PlanDomainStatus


@dataclass(frozen=True)
class SurfaceReport:
    """What one hostname serves one viewer, and the state it derives from."""

    plan_identifier: str
    hostname: str
    base_path: str
    deployment_environment: str
    is_preview: bool
    is_launched: bool
    status: PlanDomainStatus

    @property
    def key(self) -> str:
        """
        A stable identifier for this surface.

        Keyed on hostname *and* base path because one hostname can serve several plans on a
        multi-plan site, and a report keyed on the hostname alone would silently collapse them.
        """
        return f'{self.hostname}{self.base_path or ""}'

    @property
    def url(self) -> str:
        return f'https://{self.key}'

    def as_dict(self) -> dict[str, object]:
        return {
            'key': self.key,
            'plan': self.plan_identifier,
            'hostname': self.hostname,
            'base_path': self.base_path or '',
            'deployment_environment': self.deployment_environment or '',
            'is_preview': self.is_preview,
            'is_launched': self.is_launched,
            'status': self.status.value,
        }


def describe_surface(domain: PlanDomain, user: UserOrAnon | None) -> SurfaceReport:
    return SurfaceReport(
        plan_identifier=domain.plan.identifier,
        hostname=domain.hostname,
        base_path=domain.base_path or '',
        deployment_environment=domain.deployment_environment or '',
        is_preview=domain.is_preview_surface,
        is_launched=domain.is_launched,
        status=domain.status_for_user(user),
    )


def plan_surfaces(plan: Plan, user: UserOrAnon | None = None) -> list[SurfaceReport]:
    """Report every hostname this plan is served at, and what each shows `user`."""
    return [describe_surface(domain, user) for domain in plan.domains.all()]


def all_surfaces(plans: Iterable[Plan], user: UserOrAnon | None = None) -> Iterator[SurfaceReport]:
    """
    Report every hostname of every given plan.

    Ordered by surface key so two runs can be compared line by line without sorting first.
    """
    reports = [report for plan in plans for report in plan_surfaces(plan, user)]
    yield from sorted(reports, key=lambda report: report.key)
