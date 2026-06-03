from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.core.checks import Error, register as register_check

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.apps import AppConfig
    from django.core.checks import CheckMessage


@register_check(deploy=True)
def check_hostname_plan_domains(*, app_configs: Sequence[AppConfig] | None, **_kwargs: Any) -> list[CheckMessage]:
    from django.conf import settings

    domains: list[str] = getattr(settings, 'HOSTNAME_PLAN_DOMAINS', [])

    if not domains:
        return [
            Error(
                'HOSTNAME_PLAN_DOMAINS is empty.',
                hint='Set HOSTNAME_PLAN_DOMAINS to a list containing your production domain(s).',
                obj=settings,
                id='watch.D001',
            ),
        ]

    non_localhost = [d for d in domains if d != 'localhost']
    if not non_localhost:
        return [
            Error(
                'HOSTNAME_PLAN_DOMAINS contains only the default "localhost".',
                hint='Add your production domain(s) to HOSTNAME_PLAN_DOMAINS.',
                obj=settings,
                id='watch.D002',
            ),
        ]

    return []
