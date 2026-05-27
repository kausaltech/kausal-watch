"""
Smoke tests for find_broken_choice_option_refs.

These tests exercise the scanner against synthesized stale data: an option
is created, references are written, the option is removed, and the scanner
is asked to recover the stale references.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import reversion
from django.contrib.contenttypes.models import ContentType
from wagtail.models import Revision

import pytest

from actions.models import (
    Action,
    AttributeChoice,
    AttributeTypeChoiceOption,
)
from actions.tests.factories import (
    ActionFactory,
    AttributeChoiceFactory,
    AttributeTypeChoiceOptionFactory,
)
from find_broken_choice_option_refs import (
    ReconstructedOption,
    insert_reconstructed,
    reconstruct_from_reversion,
    scan_all,
    scan_live_rows,
    scan_reversion_versions,
    scan_wagtail_revisions,
)

if TYPE_CHECKING:
    from actions.models import (
        AttributeType,
    )
    from actions.models.plan import Plan
    from find_broken_choice_option_refs import (
        BrokenRef,
    )
    from users.models import User

pytestmark = pytest.mark.django_db


def _refs_for(refs: list[BrokenRef], option_pk: int) -> list[BrokenRef]:
    return [r for r in refs if r.missing_option_pk == option_pk]


def test_scan_reversion_versions_finds_stale_choice(
    plan: Plan,
    action_attribute_type__ordered_choice: AttributeType,
    user: User,
):
    action = ActionFactory.create(plan=plan)
    option = AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type__ordered_choice,
        name='Will be deleted',
    )
    attr = AttributeChoiceFactory.create(
        type=action_attribute_type__ordered_choice,
        content_object=action,
        choice=option,
    )

    with reversion.create_revision():
        reversion.set_user(user)
        reversion.add_to_revision(attr)

    stale_pk = option.pk
    # CASCADE will drop both the option and the live AttributeChoice; the
    # reversion Version row stays behind with the stale `choice` PK.
    option.delete()
    assert not AttributeChoice.objects.filter(pk=attr.pk).exists()

    refs = scan_reversion_versions()
    matching = _refs_for(refs, stale_pk)

    assert matching, 'expected at least one stale reversion version reference'
    ref = matching[0]
    assert ref.source == 'reversion-version'
    assert ref.attribute_type_pk == action_attribute_type__ordered_choice.pk
    assert ref.target_model == 'action'
    assert ref.target_pk == action.pk


def test_scan_wagtail_revisions_finds_stale_ordered_choice(
    plan: Plan,
    action_attribute_type__ordered_choice: AttributeType,
):
    action = ActionFactory.create(plan=plan)
    option = AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type__ordered_choice,
        name='Will be deleted',
    )
    stale_pk = option.pk

    Revision.objects.create(
        content_type=ContentType.objects.get_for_model(Action),
        base_content_type=ContentType.objects.get_for_model(Action),
        object_id=str(action.pk),
        content=json.loads(
            json.dumps({
                'attributes': {
                    'ordered_choice': {
                        str(action_attribute_type__ordered_choice.pk): stale_pk,
                    },
                },
            }),
        ),
    )
    option.delete()

    refs = scan_wagtail_revisions()
    matching = _refs_for(refs, stale_pk)

    assert matching, 'expected at least one stale wagtail revision reference'
    ref = matching[0]
    assert ref.source == 'wagtail-revision'
    assert ref.attribute_type_pk == action_attribute_type__ordered_choice.pk
    assert ref.target_model == 'action'
    assert ref.target_pk == action.pk
    assert ref.extra == 'format=ordered_choice'


def test_scan_wagtail_revisions_finds_stale_optional_choice(
    plan: Plan,
    action_attribute_type__optional_choice: AttributeType,
):
    action = ActionFactory.create(plan=plan)
    option = AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type__optional_choice,
        name='Will be deleted',
    )
    stale_pk = option.pk

    Revision.objects.create(
        content_type=ContentType.objects.get_for_model(Action),
        base_content_type=ContentType.objects.get_for_model(Action),
        object_id=str(action.pk),
        content=json.loads(
            json.dumps({
                'attributes': {
                    'optional_choice': {
                        str(action_attribute_type__optional_choice.pk): {
                            'choice': stale_pk,
                            'text': {'text': 'preserved'},
                        },
                    },
                },
            }),
        ),
    )
    option.delete()

    refs = scan_wagtail_revisions()
    matching = _refs_for(refs, stale_pk)

    assert matching, 'expected at least one stale optional_choice reference'
    assert matching[0].extra == 'format=optional_choice'


def test_scan_live_rows_runs_clean_when_no_orphans(
    plan: Plan,
    action_attribute_type__ordered_choice: AttributeType,
):
    # The orphan case is a data-corruption scenario produced by raw SQL or
    # partial restores; producing one inside pytest-django's transaction is
    # awkward (ALTER TABLE is blocked by pending trigger events). Verify the
    # function at least runs cleanly when all live rows resolve to existing
    # options — the implementation is a straightforward NOT-IN exclusion.
    action = ActionFactory.create(plan=plan)
    option = AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type__ordered_choice,
        name='Healthy',
    )
    AttributeChoiceFactory.create(
        type=action_attribute_type__ordered_choice,
        content_object=action,
        choice=option,
    )

    assert scan_live_rows() == []


def test_scan_all_returns_empty_when_clean(
    plan: Plan,
    action_attribute_type__ordered_choice: AttributeType,
):
    # An existing, well-formed option must not appear in the broken list.
    AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type__ordered_choice,
        name='Healthy',
    )
    refs = scan_all()
    assert refs == []


# =============================================================================
# Reconstruction from reversion
# =============================================================================


def test_reconstruct_from_reversion_finds_last_save_state(
    action_attribute_type__ordered_choice: AttributeType,
    user: User,
):
    # Save the option twice with different names so we can assert the
    # reconstruction picks the most recent revision.
    with reversion.create_revision():
        reversion.set_user(user)
        option = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Original name',
            identifier='original-identifier',
        )
        reversion.add_to_revision(option)

    with reversion.create_revision():
        reversion.set_user(user)
        option.name = 'Renamed before delete'
        option.save()
        reversion.add_to_revision(option)

    stale_pk = option.pk
    type_pk = action_attribute_type__ordered_choice.pk
    expected_order = option.order
    option.delete()

    found, needs_backup = reconstruct_from_reversion([stale_pk])

    assert needs_backup == []
    assert stale_pk in found
    recovered = found[stale_pk]
    assert recovered.name == 'Renamed before delete'
    assert recovered.identifier  # autoslug should have set this
    assert recovered.type_id == type_pk
    assert recovered.order == expected_order


def test_reconstruct_from_reversion_flags_pks_without_versions(
    action_attribute_type__ordered_choice: AttributeType,
):
    # Create an option *outside* a reversion revision so no Version row is
    # written. We do this by bypassing the manager entirely via raw create
    # then immediately taking its pk and deleting the row.
    option = AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type__ordered_choice,
        name='Never reversion-ed',
    )
    stale_pk = option.pk
    option.delete()

    # Sanity: there should be no Version row for this PK. The factory does
    # not wrap creation in reversion.create_revision(), and we deleted the
    # option without one either.
    from reversion.models import Version

    ct = ContentType.objects.get_for_model(AttributeTypeChoiceOption)
    assert not Version.objects.filter(content_type=ct, object_id=str(stale_pk)).exists()

    found, needs_backup = reconstruct_from_reversion([stale_pk])

    assert found == {}
    assert needs_backup == [stale_pk]


def test_reconstruct_from_reversion_handles_mixed_set(
    action_attribute_type__ordered_choice: AttributeType,
    user: User,
):
    # One option with reversion history, one without.
    with reversion.create_revision():
        reversion.set_user(user)
        recoverable = AttributeTypeChoiceOptionFactory.create(
            type=action_attribute_type__ordered_choice,
            name='Recoverable',
        )
        reversion.add_to_revision(recoverable)

    unrecoverable = AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type__ordered_choice,
        name='Unrecoverable',
    )

    recoverable_pk = recoverable.pk
    unrecoverable_pk = unrecoverable.pk
    recoverable.delete()
    unrecoverable.delete()

    found, needs_backup = reconstruct_from_reversion([recoverable_pk, unrecoverable_pk])

    assert set(found) == {recoverable_pk}
    assert found[recoverable_pk].name == 'Recoverable'
    assert needs_backup == [unrecoverable_pk]


def test_reconstruct_from_reversion_with_empty_input():
    found, needs_backup = reconstruct_from_reversion([])
    assert found == {}
    assert needs_backup == []


# =============================================================================
# insert_reconstructed
# =============================================================================


def _reconstructed(
    pk: int,
    *,
    type_id: int,
    name: str = 'Restored',
    identifier: str = 'restored',
    order: int = 1,
) -> ReconstructedOption:
    return ReconstructedOption(
        pk=pk,
        name=name,
        identifier=identifier,
        type_id=type_id,
        order=order,
        source_version_pk=0,
        revision_date='2026-01-01T00:00:00+00:00',
    )


def test_insert_reconstructed_dry_run_does_not_write(
    action_attribute_type__ordered_choice: AttributeType,
):
    pk = 99001
    opt = _reconstructed(pk, type_id=action_attribute_type__ordered_choice.pk)

    results = insert_reconstructed({pk: opt}, dry_run=True)

    assert len(results) == 1
    assert results[0].status == 'inserted'
    assert '(dry_run)' in results[0].detail
    assert not AttributeTypeChoiceOption.objects.filter(pk=pk).exists()


def test_insert_reconstructed_writes_archived_row_with_original_pk(
    action_attribute_type__ordered_choice: AttributeType,
):
    pk = 99002
    opt = _reconstructed(
        pk,
        type_id=action_attribute_type__ordered_choice.pk,
        name='Was deleted',
        identifier='was-deleted',
    )

    results = insert_reconstructed({pk: opt}, dry_run=False)

    assert results[0].status == 'inserted'
    row = AttributeTypeChoiceOption.objects.get(pk=pk)
    assert row.is_active is False
    assert row.name == 'Was deleted'
    assert row.identifier == 'was-deleted'
    assert row.type_id == action_attribute_type__ordered_choice.pk


def test_insert_reconstructed_restores_attribute_choice_resolution(
    plan: Plan,
    action_attribute_type__ordered_choice: AttributeType,
):
    # Simulate the production scenario: an option is deleted but a reference
    # remains (we use a constructed AttributeChoice with a synthetic stale
    # choice_id, mimicking what ActionSnapshot does at render time).
    pk = 99003
    opt = _reconstructed(
        pk,
        type_id=action_attribute_type__ordered_choice.pk,
        name='Original label',
        identifier='original-label',
    )

    insert_reconstructed({pk: opt}, dry_run=False)

    # The synthetic AttributeChoice with choice_id=pk now resolves cleanly.
    stale_instance = AttributeChoice(
        type=action_attribute_type__ordered_choice,
        content_type=ContentType.objects.get_for_model(Action),
        object_id=1,
        choice_id=pk,
    )
    assert str(stale_instance) == 'Original label'


def test_insert_reconstructed_skips_existing_pk(
    action_attribute_type__ordered_choice: AttributeType,
):
    existing = AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type__ordered_choice,
        name='Already here',
    )
    opt = _reconstructed(
        existing.pk,
        type_id=action_attribute_type__ordered_choice.pk,
        name='Stale reconstruction',
    )

    results = insert_reconstructed({existing.pk: opt}, dry_run=False)

    assert results[0].status == 'skipped-already-exists'
    existing.refresh_from_db()
    assert existing.name == 'Already here'


def test_insert_reconstructed_skips_when_type_missing(plan: Plan):
    del plan  # only needed so factories work; the actual type is gone
    opt = _reconstructed(99004, type_id=999999, name='Orphaned option')

    results = insert_reconstructed({99004: opt}, dry_run=False)

    assert results[0].status == 'skipped-type-missing'
    assert not AttributeTypeChoiceOption.objects.filter(pk=99004).exists()


def test_insert_reconstructed_renames_identifier_on_collision(
    action_attribute_type__ordered_choice: AttributeType,
):
    # The active option's name is what AutoSlugField will turn into its
    # identifier (always_update=True overrides any factory-passed value), so
    # 'Clashing name' → 'clashing-name'.
    existing = AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type__ordered_choice,
        name='Clashing name',
    )
    assert existing.identifier == 'clashing-name'

    pk = 99005
    opt = _reconstructed(
        pk,
        type_id=action_attribute_type__ordered_choice.pk,
        name='Restored option',
        identifier='clashing-name',
    )

    insert_reconstructed({pk: opt}, dry_run=False)

    row = AttributeTypeChoiceOption.objects.get(pk=pk)
    assert row.identifier == f'clashing-name-archived-{pk}'


def test_insert_reconstructed_orders_above_active_rows(
    action_attribute_type__ordered_choice: AttributeType,
):
    existing = AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type__ordered_choice,
        name='Active',
    )
    pk = 99006
    opt = _reconstructed(
        pk,
        type_id=action_attribute_type__ordered_choice.pk,
        # Original order doesn't matter — we always park archived rows above
        # the active sequence.
        order=0,
    )

    insert_reconstructed({pk: opt}, dry_run=False)

    row = AttributeTypeChoiceOption.objects.get(pk=pk)
    assert row.order > existing.order


def test_insert_reconstructed_handles_multiple_rows_on_same_type(
    action_attribute_type__ordered_choice: AttributeType,
):
    # Two restorations on the same type must not collide on (type, order)
    # — this is the regression scenario that produced
    # `duplicate key value violates unique constraint "unique_order_per_type"`.
    existing = AttributeTypeChoiceOptionFactory.create(
        type=action_attribute_type__ordered_choice,
        name='Active row',
    )
    options = {
        99010: _reconstructed(99010, type_id=action_attribute_type__ordered_choice.pk, name='First'),
        99011: _reconstructed(99011, type_id=action_attribute_type__ordered_choice.pk, name='Second'),
        99012: _reconstructed(99012, type_id=action_attribute_type__ordered_choice.pk, name='Third'),
    }

    results = insert_reconstructed(options, dry_run=False)

    assert all(r.status == 'inserted' for r in results), results
    rows = AttributeTypeChoiceOption.objects.filter(pk__in=options).order_by('pk')
    orders = [row.order for row in rows]
    assert len(orders) == 3
    assert len(set(orders)) == 3, 'each restored row must get a distinct order'
    assert all(order > existing.order for order in orders), 'archived orders sit above active'


def test_insert_reconstructed_handles_identifier_collision_within_batch(
    action_attribute_type__ordered_choice: AttributeType,
):
    # Two restorations whose original identifiers were the same must end up
    # with distinct identifiers.
    options = {
        99020: _reconstructed(
            99020,
            type_id=action_attribute_type__ordered_choice.pk,
            name='Same name',
            identifier='same-id',
        ),
        99021: _reconstructed(
            99021,
            type_id=action_attribute_type__ordered_choice.pk,
            name='Same name',
            identifier='same-id',
        ),
    }

    insert_reconstructed(options, dry_run=False)

    identifiers = set(
        AttributeTypeChoiceOption.objects.filter(pk__in=options).values_list('identifier', flat=True),
    )
    assert len(identifiers) == 2, f'expected distinct identifiers, got {identifiers}'


def test_insert_reconstructed_skips_missing_fields(
    action_attribute_type__ordered_choice: AttributeType,
):
    opt = ReconstructedOption(
        pk=99007,
        name=None,
        identifier=None,
        type_id=action_attribute_type__ordered_choice.pk,
        order=None,
        source_version_pk=0,
        revision_date='2026-01-01T00:00:00+00:00',
    )

    results = insert_reconstructed([opt], dry_run=False)

    assert results[0].status == 'skipped-missing-fields'
    assert not AttributeTypeChoiceOption.objects.filter(pk=99007).exists()
