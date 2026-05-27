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
)
from actions.tests.factories import (
    ActionFactory,
    AttributeChoiceFactory,
    AttributeTypeChoiceOptionFactory,
)
from find_broken_choice_option_refs import (
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
