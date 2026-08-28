from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from wagtail.signals import (
    task_cancelled,
    task_submitted,
    workflow_approved,
    workflow_rejected,
    workflow_submitted,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_SUPPRESSED_SIGNALS = (
    workflow_approved,
    workflow_rejected,
    workflow_submitted,
    task_submitted,
    task_cancelled,
)


@contextmanager
def suppress_workflow_notifications() -> Iterator[None]:
    saved = []
    for sig in _SUPPRESSED_SIGNALS:
        with sig.lock:
            saved.append((sig, list(sig.receivers)))
            sig.receivers = []
    try:
        yield
    finally:
        for sig, receivers in saved:
            with sig.lock:
                sig.receivers = receivers
