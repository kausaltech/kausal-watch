"""
Concurrency regression test for the bulk action-attribute write path.

Reproduces Sentry 17649 — an ``IntegrityError`` on
``actions_attributechoice_type_id_content_type_id__9ad7174d_uniq`` raised from
``BulkListSerializer`` → deferred ops → ``QuerySet.bulk_create()`` — which
surfaces to the grid editor as the frontend "REST error 500" (Sentry 17218).

The race: every bulk request builds its "existing attributes" snapshot once, at
serializer construction (``AttributeFieldSerializer.initialize_cache_context``).
If a second request builds its snapshot before the first one commits, it still
believes the attribute is absent, emits a ``create`` op, and its final
``bulk_create()`` violates the ``unique_together`` on
``(type, content_type, object_id)`` — one choice value per attribute type per
action already exists.

Rather than running two live requests on two threads (which needs real commits
and therefore a ``transaction=True`` test with its table-truncating teardown
flush), we stage the interleaving deterministically on a single connection. The
"winner" request runs start-to-finish first. The "loser" request runs afterwards,
but its attribute snapshot is replaced with the one the winner took before it
wrote anything — i.e. the loser behaves as if it had built its snapshot at the
same moment as the winner, before the winner's write landed. Both send the same
base ``version``, exactly as two grid tabs (or a double-submit) would. Everything
else the loser does (version check, row lock, writes) runs against the real,
post-winner database state.

The assertions describe the desired contract and are agnostic to which fix
lands: an upsert / row-lock approach (both requests succeed) or an
optimistic-concurrency approach (one request is rejected with 409). Before the
fix, the loser crashes with a 500; after it, both resolve cleanly to a single
row.
"""

from __future__ import annotations

from typing import Any

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from rest_framework.test import APIClient

import pytest

from actions.api import ActionSerializer
from actions.models import Action
from actions.models.attributes import AttributeChoice, AttributeType
from actions.tests.factories import (
    ActionFactory,
    AttributeTypeChoiceOptionFactory,
    AttributeTypeFactory,
)

pytestmark = pytest.mark.django_db


def _copy_attribute_values(attribute_values: dict[str, dict[int, list[Any]]]) -> dict[str, dict[int, list[Any]]]:
    return {fmt: {pk: list(values) for pk, values in by_pk.items()} for fmt, by_pk in attribute_values.items()}


def test_concurrent_bulk_attribute_writes_do_not_500(plan, plan_admin_user, monkeypatch):
    action = ActionFactory.create(plan=plan)
    action_ct = ContentType.objects.get_for_model(Action)
    attribute_type = AttributeTypeFactory.create(
        object_content_type=action_ct,
        scope=plan,
        format=AttributeType.AttributeFormat.ORDERED_CHOICE,
    )
    option = AttributeTypeChoiceOptionFactory.create(type=attribute_type)

    url = reverse('action-list', args=(plan.pk,))
    # Mirror the real grid payload: it sends `version` per row (the optimistic-
    # concurrency token the client last saw), plus the choice value it wants to set.
    payload = [
        {
            'id': action.pk,
            'identifier': action.identifier,
            'name': action.name,
            'version': action.version,
            'choice_attributes': {attribute_type.identifier: option.pk},
        },
    ]

    # The winner's first snapshot is taken at serializer construction, before it
    # writes anything. The loser's first snapshot is swapped for that one, as if
    # both requests had built their snapshots at the same moment.
    current_role: str | None = None
    stale_snapshot: dict[str, dict[int, list[Any]]] | None = None
    loser_staged = False
    original_initialize = ActionSerializer.initialize_cache_context

    def staged_initialize_cache_context(self):
        nonlocal stale_snapshot, loser_staged
        original_initialize(self)
        cache = self.context.get('_cache')
        if cache is None:
            return
        if current_role == 'winner' and stale_snapshot is None:
            stale_snapshot = _copy_attribute_values(cache['attribute_values'])
        elif current_role == 'loser' and not loser_staged:
            assert stale_snapshot is not None, 'winner never built its snapshot'
            for field_name in self._attribute_fields:
                self.fields[field_name].context['_cache']['attribute_values'] = _copy_attribute_values(stale_snapshot)
            loser_staged = True

    monkeypatch.setattr(ActionSerializer, 'initialize_cache_context', staged_initialize_cache_context)

    def do_request(role: str) -> int:
        nonlocal current_role
        current_role = role
        client = APIClient()
        # Capture a 500 as a response instead of re-raising into the test.
        client.raise_request_exception = False
        client.force_authenticate(plan_admin_user)
        return client.put(url, data=payload, format='json').status_code

    results = {'winner': do_request('winner'), 'loser': do_request('loser')}
    assert loser_staged, 'loser never built its snapshot'

    outcomes = list(results.values())

    # The core regression: neither concurrent write may crash with a 500 /
    # IntegrityError.
    assert 500 not in outcomes, results

    # Fix-agnostic contract: each request either succeeds (upsert / lock) or is
    # cleanly rejected with a conflict (optimistic concurrency); at least one
    # succeeds and at most one is rejected.
    assert all(o in (200, 409) for o in outcomes), results
    assert 200 in outcomes, results
    assert outcomes.count(409) <= 1, results

    # However it is resolved, the data must converge to exactly one row.
    assert (
        AttributeChoice.objects.filter(
            type=attribute_type,
            content_type=action_ct,
            object_id=action.pk,
        ).count()
        == 1
    )
