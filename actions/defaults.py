from __future__ import annotations

from typing import TYPE_CHECKING, NotRequired, TypedDict

from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from django_stubs_ext.aliases import StrOrPromise  # pyright: ignore


class DefaultActionStatus(TypedDict):
    identifier: str
    name: StrOrPromise
    is_completed: NotRequired[bool]


DEFAULT_ACTION_STATUSES: list[DefaultActionStatus] = [
    {
        'identifier': 'on_time',
        'name': _("On time"),
    }, {
        'identifier': 'late',
        'name': _("Late"),
    }, {
        'identifier': 'cancelled',
        'name': _("Cancelled or postponed"),
        'is_completed': True,
    },
]

DEFAULT_ACTION_IMPLEMENTATION_PHASES = [
    {
        'identifier': 'not_started',
        'name': _("Not started"),
    }, {
        'identifier': 'planning',
        'name': _("Planning"),
    }, {
        'identifier': 'implementation',
        'name': _("Implementation"),
    }, {
        'identifier': 'completed',
        'name': _("Completed"),
    },
]
