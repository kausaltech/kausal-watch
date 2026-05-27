"""
Find broken AttributeTypeChoiceOption references.

Scans three sources for references to AttributeTypeChoiceOption rows that
no longer exist in the database:

1. django-reversion Versions of AttributeChoice / AttributeChoiceWithText.
   These power report snapshots and admin revision history. The `choice`
   PK lives in `serialized_data` (a JSON-encoded text field).

2. Wagtail Revisions of any model with attribute drafts (Action, Category,
   Pledge). The choice PK lives in `content['attributes'][<format>][<at_pk>]`,
   either as a bare int (ordered_choice / unordered_choice) or as a dict
   {'choice': <pk>, 'text': ...} (optional_choice).

3. Live AttributeChoice / AttributeChoiceWithText rows whose `choice_id`
   doesn't resolve to an AttributeTypeChoiceOption. Under normal CASCADE
   behaviour these should never exist; if any are found, something has
   bypassed the FK (raw SQL, partial restore, etc.).

Usage from shell_plus:

    from find_broken_choice_option_refs import scan_all, print_report
    refs = scan_all()
    print_report(refs)

    # Or scan one source at a time:
    from find_broken_choice_option_refs import (
        scan_reversion_versions, scan_wagtail_revisions, scan_live_rows,
    )

Each scan returns a list of `BrokenRef`s; `print_report` groups them by
the missing AttributeTypeChoiceOption PK so you can see, for a given
deleted option, every place that still references it.

Once you have the set of missing PKs, `reconstruct_from_reversion()` reads
the django-reversion Versions of AttributeTypeChoiceOption itself in the
live DB to recover each option's last-known name / identifier / type / order.
PKs without any Version row are returned separately so they can be looked
up in DB backups.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.contrib.contenttypes.models import ContentType

from actions.models import (
    AttributeChoice,
    AttributeChoiceWithText,
    AttributeTypeChoiceOption,
)

if TYPE_CHECKING:
    from collections.abc import Iterable


@dataclass
class BrokenRef:
    source: str
    """One of: 'reversion-version', 'wagtail-revision',
    'live-attribute-choice', 'live-attribute-choice-with-text'."""

    source_pk: int
    """PK of the row that contains the stale reference."""

    missing_option_pk: int
    """The AttributeTypeChoiceOption PK that no longer exists."""

    attribute_type_pk: int | None = None
    """The AttributeType PK, when recoverable from the source row."""

    target_model: str | None = None
    """e.g. 'action', 'category' — the model the attribute was attached to."""

    target_pk: int | None = None
    """PK of the target row (e.g. the Action that owned the attribute)."""

    extra: str = ''
    """Free-form context, e.g. 'format=optional_choice'."""


def _existing_option_pks() -> set[int]:
    return set(AttributeTypeChoiceOption.objects.values_list('pk', flat=True))


def _parse_serialized_choice(serialized: str) -> tuple[int | None, int | None, int | None, int | None]:
    """
    Return (choice_pk, type_pk, content_type_id, object_id) from a reversion serialized_data string.

    Returns Nones if the string can't be parsed or doesn't contain a choice.
    """
    try:
        entries = json.loads(serialized)
    except ValueError:
        return None, None, None, None
    if not isinstance(entries, list) or not entries:
        return None, None, None, None
    fields = entries[0].get('fields') if isinstance(entries[0], dict) else None
    if not isinstance(fields, dict):
        return None, None, None, None
    choice = fields.get('choice')
    if not isinstance(choice, int):
        return None, None, None, None
    type_pk = fields.get('type') if isinstance(fields.get('type'), int) else None
    ct_id = fields.get('content_type') if isinstance(fields.get('content_type'), int) else None
    obj_id = fields.get('object_id') if isinstance(fields.get('object_id'), int) else None
    return choice, type_pk, ct_id, obj_id


def scan_reversion_versions(existing: set[int] | None = None) -> list[BrokenRef]:
    """Find references in django-reversion Versions of AttributeChoice / WithText."""
    from reversion.models import Version

    if existing is None:
        existing = _existing_option_pks()

    cts = ContentType.objects.filter(
        app_label='actions',
        model__in=('attributechoice', 'attributechoicewithtext'),
    )
    ct_by_id = {ct.pk: ct for ct in ContentType.objects.all()}

    results: list[BrokenRef] = []
    versions = Version.objects.filter(content_type__in=cts).iterator(chunk_size=1000)
    for version in versions:
        choice_pk, type_pk, target_ct_id, target_pk = _parse_serialized_choice(version.serialized_data)
        if choice_pk is None or choice_pk in existing:
            continue
        target_model = ct_by_id[target_ct_id].model if target_ct_id in ct_by_id else None
        results.append(
            BrokenRef(
                source='reversion-version',
                source_pk=version.pk,
                missing_option_pk=choice_pk,
                attribute_type_pk=type_pk,
                target_model=target_model,
                target_pk=target_pk,
            ),
        )
    return results


def _extract_option_pk(format_key: str, value: object) -> int | None:
    if format_key in ('ordered_choice', 'unordered_choice') and isinstance(value, int):
        return value
    if format_key == 'optional_choice' and isinstance(value, dict):
        choice = value.get('choice')
        return choice if isinstance(choice, int) else None
    return None


def _iter_revision_choice_refs(
    revision_content: object,
) -> Iterable[tuple[str, int | None, int]]:
    """Yield (format_key, attr_type_pk, option_pk) triples from one revision's content."""
    if not isinstance(revision_content, dict):
        return
    attributes = revision_content.get('attributes')
    if not isinstance(attributes, dict):
        return
    for format_key, type_values in attributes.items():
        if not isinstance(type_values, dict):
            continue
        for type_pk_str, value in type_values.items():
            option_pk = _extract_option_pk(format_key, value)
            if option_pk is None:
                continue
            try:
                attr_type_pk = int(type_pk_str)
            except ValueError:
                attr_type_pk = None
            yield format_key, attr_type_pk, option_pk


def scan_wagtail_revisions(existing: set[int] | None = None) -> list[BrokenRef]:
    """Find references in Wagtail Revisions of attribute-bearing models."""
    from wagtail.models import Revision

    if existing is None:
        existing = _existing_option_pks()

    target_cts = ContentType.objects.filter(
        app_label='actions',
        model__in=('action', 'category', 'pledge'),
    )
    target_model_by_ct: dict[int, str] = {ct.pk: ct.model for ct in target_cts}

    results: list[BrokenRef] = []
    revisions = (
        Revision.objects
        .filter(content_type__in=target_cts)
        .only('id', 'content', 'content_type_id', 'object_id')
        .iterator(chunk_size=500)
    )
    for revision in revisions:
        for format_key, attr_type_pk, option_pk in _iter_revision_choice_refs(revision.content):
            if option_pk in existing:
                continue
            try:
                target_pk = int(revision.object_id)
            except ValueError:
                target_pk = None
            results.append(
                BrokenRef(
                    source='wagtail-revision',
                    source_pk=revision.pk,
                    missing_option_pk=option_pk,
                    attribute_type_pk=attr_type_pk,
                    target_model=target_model_by_ct.get(revision.content_type_id),
                    target_pk=target_pk,
                    extra=f'format={format_key}',
                ),
            )
    return results


def scan_live_rows(existing: set[int] | None = None) -> list[BrokenRef]:
    """Find live AttributeChoice / WithText rows pointing at a missing option."""
    if existing is None:
        existing = _existing_option_pks()

    ct_by_id = {ct.pk: ct for ct in ContentType.objects.all()}
    results: list[BrokenRef] = []
    for cls, source_label in (
        (AttributeChoice, 'live-attribute-choice'),
        (AttributeChoiceWithText, 'live-attribute-choice-with-text'),
    ):
        orphans = cls.objects.filter(choice_id__isnull=False).exclude(choice_id__in=existing).iterator(chunk_size=1000)
        for row in orphans:
            target_model = ct_by_id[row.content_type_id].model if row.content_type_id in ct_by_id else None
            results.append(
                BrokenRef(
                    source=source_label,
                    source_pk=row.pk,
                    missing_option_pk=row.choice_id,
                    attribute_type_pk=row.type_id,
                    target_model=target_model,
                    target_pk=row.object_id,
                ),
            )
    return results


def scan_all() -> list[BrokenRef]:
    """Scan all three sources and return broken references."""
    existing = _existing_option_pks()
    return [
        *scan_reversion_versions(existing),
        *scan_wagtail_revisions(existing),
        *scan_live_rows(existing),
    ]


@dataclass
class ReconstructedOption:
    pk: int
    """The (currently missing) AttributeTypeChoiceOption PK."""

    name: str | None
    identifier: str | None
    type_id: int | None
    order: int | None

    source_version_pk: int
    """The reversion Version row this data was reconstructed from."""

    revision_date: str
    """ISO timestamp of the Version's revision (for audit)."""


def reconstruct_from_reversion(
    missing_pks: Iterable[int],
) -> tuple[dict[int, ReconstructedOption], list[int]]:
    """
    Recover last-known state of deleted AttributeTypeChoiceOptions from reversion.

    For each PK in `missing_pks`, find the most recent reversion Version of
    AttributeTypeChoiceOption with that `object_id` and extract its serialized
    fields.

    Returns `(found, needs_backup)`:

    - `found`: {pk: ReconstructedOption} for PKs that had at least one Version.
    - `needs_backup`: list of PKs with no Version in the live DB. For these
      you'll need to query a backup that pre-dates the deletion.
    """
    from reversion.models import Version

    pk_set = {int(pk) for pk in missing_pks}
    if not pk_set:
        return {}, []

    ct = ContentType.objects.get(app_label='actions', model='attributetypechoiceoption')
    versions = (
        Version.objects
        .filter(content_type=ct, object_id__in=[str(pk) for pk in pk_set])
        .select_related('revision')
        .order_by('-revision__date_created')
    )

    found: dict[int, ReconstructedOption] = {}
    for version in versions:
        try:
            pk = int(version.object_id)
        except ValueError:
            continue
        if pk in found:
            # We've already captured the most recent Version for this PK.
            continue
        try:
            entries = json.loads(version.serialized_data)
        except ValueError:
            continue
        if not isinstance(entries, list) or not entries:
            continue
        fields = entries[0].get('fields') if isinstance(entries[0], dict) else None
        if not isinstance(fields, dict):
            continue
        found[pk] = ReconstructedOption(
            pk=pk,
            name=fields.get('name') if isinstance(fields.get('name'), str) else None,
            identifier=fields.get('identifier') if isinstance(fields.get('identifier'), str) else None,
            type_id=fields.get('type') if isinstance(fields.get('type'), int) else None,
            order=fields.get('order') if isinstance(fields.get('order'), int) else None,
            source_version_pk=version.pk,
            revision_date=version.revision.date_created.isoformat(),
        )

    needs_backup = sorted(pk_set - set(found))
    return found, needs_backup


@dataclass
class InsertResult:
    pk: int
    status: str
    """One of: 'inserted', 'skipped-already-exists', 'skipped-type-missing',
    'skipped-missing-fields'."""

    detail: str = ''


def insert_reconstructed(
    options: dict[int, ReconstructedOption] | Iterable[ReconstructedOption],
    *,
    dry_run: bool = True,
) -> list[InsertResult]:
    """
    Re-insert deleted AttributeTypeChoiceOptions as archived rows.

    Each row is inserted with `is_active=False` and an `order` parked above
    all existing siblings of the same type, so stale FK references (reversion
    Versions, Wagtail Revisions, etc.) resolve again. Pickers and the GraphQL
    listing skip archived options, so end users don't see them — but
    historical reports render the option's original name instead of
    "Missing value".

    Skip rules (each row reported in the result with a status):

    - 'skipped-already-exists': a row with that PK is already in the DB
      (someone may have re-created the option since deletion).
    - 'skipped-type-missing': the original `type_id` no longer exists, so we
      can't link the row anywhere.
    - 'skipped-missing-fields': the reconstructed data lacks one of the
      required fields (name, identifier, type_id, order).

    If the reconstructed `identifier` is already taken on the same type, a
    suffix `-archived-<pk>` is appended so the unique constraint holds. The
    FK from AttributeChoice points at the PK, not the identifier, so renaming
    is safe.

    The full insert runs in a single transaction. Pass `dry_run=False` to
    write; the default reports what would happen without touching the DB.
    """
    from django.db import transaction

    if isinstance(options, dict):
        items = list(options.values())
    else:
        items = list(options)

    from actions.models import AttributeType

    existing_pks = set(AttributeTypeChoiceOption.objects.values_list('pk', flat=True))
    type_pks = set(AttributeType.objects.values_list('pk', flat=True))

    results: list[InsertResult] = []
    to_insert: list[tuple[ReconstructedOption, str, int]] = []
    for opt in items:
        if opt.pk in existing_pks:
            results.append(InsertResult(pk=opt.pk, status='skipped-already-exists'))
            continue
        if opt.name is None or opt.identifier is None or opt.type_id is None or opt.order is None:
            results.append(
                InsertResult(
                    pk=opt.pk,
                    status='skipped-missing-fields',
                    detail=(f'name={opt.name!r} identifier={opt.identifier!r} type_id={opt.type_id} order={opt.order}'),
                ),
            )
            continue
        if opt.type_id not in type_pks:
            results.append(
                InsertResult(
                    pk=opt.pk,
                    status='skipped-type-missing',
                    detail=f'type_id={opt.type_id} no longer exists',
                ),
            )
            continue

        identifier = _pick_identifier(opt.identifier, opt.type_id, opt.pk)
        order = _pick_archived_order(opt.type_id)
        to_insert.append((opt, identifier, order))

    if dry_run:
        for opt, identifier, order in to_insert:
            results.append(
                InsertResult(
                    pk=opt.pk,
                    status='inserted',
                    detail=f'(dry_run) identifier={identifier!r} order={order}',
                ),
            )
        return results

    with transaction.atomic():
        for opt, identifier, order in to_insert:
            # `identifier` is an AutoSlugField with always_update=True; it will
            # be overwritten from `name` on save. Create first, then UPDATE the
            # identifier directly so the original value is preserved.
            AttributeTypeChoiceOption.objects.create(
                pk=opt.pk,
                name=opt.name,
                type_id=opt.type_id,
                order=order,
                is_active=False,
            )
            AttributeTypeChoiceOption.objects.filter(pk=opt.pk).update(identifier=identifier)
            results.append(
                InsertResult(
                    pk=opt.pk,
                    status='inserted',
                    detail=f'identifier={identifier!r} order={order}',
                ),
            )
    return results


def _pick_identifier(original: str, type_id: int, pk: int) -> str:
    """Return an identifier that's unique on the type, suffixing if needed."""
    taken = set(
        AttributeTypeChoiceOption.objects.filter(type_id=type_id).values_list('identifier', flat=True),
    )
    if original not in taken:
        return original
    suffixed = f'{original}-archived-{pk}'
    if suffixed in taken:
        # Extremely unlikely (would require a previous restoration cycle for
        # the same PK) but stay defensive.
        return f'{original}-archived-{pk}-{len(taken)}'
    return suffixed


def _pick_archived_order(type_id: int) -> int:
    """Return an order value above any existing sibling for the same type."""
    from django.db.models import Max

    current = AttributeTypeChoiceOption.objects.filter(type_id=type_id).aggregate(m=Max('order'))['m']
    return (current if current is not None else 0) + 1


def print_reconstruction(
    found: dict[int, ReconstructedOption],
    needs_backup: list[int],
) -> None:
    """Pretty-print a reconstruction result."""
    if found:
        print(f'Recovered {len(found)} AttributeTypeChoiceOption(s) from reversion:')
        for pk in sorted(found):
            opt = found[pk]
            print(
                f'  pk={pk}: name={opt.name!r}, identifier={opt.identifier!r}, '
                f'type_id={opt.type_id}, order={opt.order} '
                f'(Version pk={opt.source_version_pk}, {opt.revision_date})',
            )
        print()
    if needs_backup:
        print(
            f'{len(needs_backup)} PK(s) have no reversion Version and need a backup lookup:',
        )
        print(f'  {needs_backup}')
        print()
    if not found and not needs_backup:
        print('Nothing to reconstruct.')


def _format_example(ref: BrokenRef) -> str:
    target_bit = ''
    if ref.target_model and ref.target_pk is not None:
        target_bit = f' on {ref.target_model}={ref.target_pk}'
    extra_bit = f' [{ref.extra}]' if ref.extra else ''
    return f'    e.g. {ref.source} pk={ref.source_pk}{target_bit}{extra_bit}'


def _print_option_block(option_pk: int, ref_list: list[BrokenRef]) -> None:
    attr_type_pks = {r.attribute_type_pk for r in ref_list if r.attribute_type_pk is not None}
    attr_type_summary = f', attribute_type PK(s): {sorted(attr_type_pks)}' if attr_type_pks else ''
    print(f'AttributeTypeChoiceOption pk={option_pk}{attr_type_summary} — {len(ref_list)} reference(s):')

    by_source: dict[str, int] = defaultdict(int)
    examples_by_source: dict[str, list[BrokenRef]] = defaultdict(list)
    for ref in ref_list:
        by_source[ref.source] += 1
        if len(examples_by_source[ref.source]) < 3:
            examples_by_source[ref.source].append(ref)

    for source, count in sorted(by_source.items()):
        print(f'  {source}: {count}')
    for source in sorted(examples_by_source):
        for ref in examples_by_source[source]:
            print(_format_example(ref))
    print()


def print_report(refs: Iterable[BrokenRef]) -> None:
    """Group references by missing option PK and print a readable summary."""
    by_option: dict[int, list[BrokenRef]] = defaultdict(list)
    for ref in refs:
        by_option[ref.missing_option_pk].append(ref)

    if not by_option:
        print('No broken AttributeTypeChoiceOption references found.')
        return

    print(f'Found broken references to {len(by_option)} missing AttributeTypeChoiceOption(s):')
    print()
    for option_pk in sorted(by_option):
        _print_option_block(option_pk, by_option[option_pk])
