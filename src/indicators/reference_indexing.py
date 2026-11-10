"""
Batched reference-index refresh for bulk Indicator writes.

A bulk write suppresses Wagtail's per-row reference-index auto-update: each ``Indicator.save()``
would otherwise walk up to its Organization and rebuild that whole organization's reference index
(O(indicators in the organization)) once per row. Most bulk edits change no reference-carrying field
and leave the reference index correct, but the serializer also exposes fields that do feed the index --
the rich-text ``description`` (translated, so its content lives across the ``i18n`` column) and
``reference``, and ``organization``, which moves an indicator between organization reference
clusters. When one of those actually changes the index must still be refreshed, so the affected
organizations are rebuilt once each after the write instead of once per row.

The set of fields that feed the reference index is derived from the model rather than hardcoded, so
a new rich-text field or a new (non-ignored) foreign key is picked up automatically instead of
silently going stale.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.db.models import Field
from modelcluster.fields import ParentalKey
from wagtail.models import ReferenceIndex

if TYPE_CHECKING:
    from collections.abc import Sequence

# The indicator's reference index lives under its walk-up root; for Indicator that root is its
# Organization (an indexed snippet). Tracking this column detects a move to another organization.
_ROOT_ORGANIZATION_COLUMN = 'organization_id'

# pk -> {column: value} for the columns that feed the reference index. Comparing two snapshots tells
# us whether a bulk write changed anything the index depends on, and which organization holds it.
ReferenceState = dict[int, dict[str, Any]]


@lru_cache(maxsize=1)
def _reference_relevant_columns() -> tuple[str, ...]:
    """
    Return the Indicator columns whose value feeds the reference index.

    Derived from the model so new reference-carrying fields are covered automatically: the walk-up
    root (for relocation), the ``i18n`` JSON column that holds translated rich text, every field
    that extracts references (rich text), and every non-parental, non-ignored foreign key (which
    Wagtail records as a reference). Parental keys other than the root are skipped -- they are not
    recorded as references and do not change which organization holds the index.
    """
    from indicators.models import Indicator

    columns: set[str] = {_ROOT_ORGANIZATION_COLUMN}
    for field in Indicator._meta.get_fields():
        if getattr(field, 'name', None) == 'i18n':
            columns.add('i18n')
            continue
        if not isinstance(field, Field):
            # Reverse relations (child accessors, reverse M2M) have no column of their own.
            continue
        if hasattr(field, 'extract_references'):
            columns.add(field.attname)
        elif field.is_relation and field.many_to_one and not isinstance(field, ParentalKey):
            ignored = getattr(field, 'wagtail_reference_index_ignore', False) or getattr(
                field.related_model, 'wagtail_reference_index_ignore', False
            )
            if not ignored:
                columns.add(field.attname)
    return tuple(sorted(columns))


def snapshot_reference_state(pks: Sequence[int]) -> ReferenceState:
    """
    Capture the reference-relevant column values of the given indicators.

    A later snapshot can be compared against this one to detect whether a bulk write changed
    anything the reference index depends on, and to find the organization that holds it.
    """
    from indicators.models import Indicator

    columns = _reference_relevant_columns()
    return {
        row['pk']: {column: row[column] for column in columns}
        for row in Indicator.objects.filter(pk__in=pks).values('pk', *columns)
    }


def refresh_reference_index_after_bulk(before: ReferenceState, after: ReferenceState) -> None:
    """
    Rebuild the reference index for organizations whose indicators changed, once each.

    For every indicator whose reference-relevant columns differ between the snapshots, both its old
    and new organization are rebuilt -- an organization move must drop the reference under the old
    organization and record it under the new one. Organizations with no relevant change are skipped,
    so a bulk edit that changes no reference-carrying field does no reference-index work.
    """
    from orgs.models import Organization

    organization_ids: set[int] = set()
    for pk, after_state in after.items():
        before_state = before.get(pk)
        if before_state == after_state:
            continue
        for state in (before_state, after_state):
            if state is None:
                continue
            organization_id = state.get(_ROOT_ORGANIZATION_COLUMN)
            if organization_id is not None:
                organization_ids.add(organization_id)

    if not organization_ids:
        return

    for organization in Organization.objects.filter(pk__in=organization_ids):
        with transaction.atomic():
            ReferenceIndex.create_or_update_for_object(organization)
