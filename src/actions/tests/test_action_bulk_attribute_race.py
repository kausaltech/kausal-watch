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

Rather than relying on wall-clock timing, we drive the interleaving
deterministically. The "loser" request is parked at the very start of the write
path — after it has built its (empty) snapshot, parsed its base version, and
passed its permission check, but before it takes any lock or writes anything.
The "winner" then runs start-to-finish alone and commits; only then is the loser
released, into a world where the row it thought was untouched now exists. Both
send the same base ``version``, exactly as two grid tabs (or a double-submit)
would. Parking before any lock means the winner never blocks on the loser, and
running the two requests one-at-a-time avoids incidental shared-state races.

The assertions describe the desired contract and are agnostic to which fix
lands: an upsert / row-lock approach (both requests succeed) or an
optimistic-concurrency approach (one request is rejected with 409). Before the
fix, the loser crashes with a 500; after it, both resolve cleanly to a single
row.
"""

from __future__ import annotations

import threading

from django.contrib.contenttypes.models import ContentType
from django.db import connections
from django.db.models.signals import post_migrate
from django.urls import reverse
from rest_framework.test import APIClient

import pytest

from kausal_common.api.bulk import BulkListSerializer

from actions.models import Action
from actions.models.attributes import AttributeChoice, AttributeType
from actions.tests.factories import (
    ActionFactory,
    AttributeTypeChoiceOptionFactory,
    AttributeTypeFactory,
)

# transaction=True so each request's ATOMIC_REQUESTS transaction really commits
# and is visible to the other thread's connection (a plain `db` fixture wraps
# everything in one rolled-back transaction, which can't model a cross-request
# race).
pytestmark = pytest.mark.django_db(transaction=True)

_WAIT_TIMEOUT = 30


@pytest.fixture(autouse=True, scope='module')
def _no_permission_sync_on_flush():
    """
    Neutralise the `sync_permissions` post_migrate receiver for this module.

    `transaction=True` tests flush the DB on teardown, which re-emits
    `post_migrate`; the project's `sync_permissions` handler then re-adds
    `auth_group_permissions` rows referencing permissions that the flush has
    truncated, raising a ForeignKeyViolation at COMMIT. Django's own
    `create_permissions` receiver still runs, so permissions are recreated
    normally; we only skip the group-permission re-sync during the flush.
    """
    from actions.signals import sync_permissions

    post_migrate.disconnect(dispatch_uid='sync_app_permissions')
    yield
    post_migrate.connect(sync_permissions, dispatch_uid='sync_app_permissions')


def _is_server_error(outcome: object) -> bool:
    return isinstance(outcome, Exception) or outcome == 500


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

    # Park the loser at the start of the write path (snapshot built, version
    # parsed, permission check passed, but before any lock/write). The winner
    # runs fully and commits; then the loser is released into the conflict.
    role = threading.local()
    loser_parked = threading.Event()
    winner_committed = threading.Event()
    original_update = BulkListSerializer.update

    def patched_update(self, *args, **kwargs):
        if getattr(role, 'name', None) == 'loser':
            loser_parked.set()
            assert winner_committed.wait(timeout=_WAIT_TIMEOUT), 'winner never committed'
        return original_update(self, *args, **kwargs)

    monkeypatch.setattr(BulkListSerializer, 'update', patched_update)

    results: dict[str, object] = {}

    def do_request(name: str):
        role.name = name
        client = APIClient()
        # Capture a 500 as a response instead of re-raising into the thread.
        client.raise_request_exception = False
        client.force_authenticate(plan_admin_user)
        try:
            resp = client.put(url, data=payload, format='json')
            results[name] = resp.status_code
        except Exception as e:
            results[name] = e
        finally:
            connections.close_all()

    loser = threading.Thread(target=do_request, args=('loser',), name='loser')
    winner = threading.Thread(target=do_request, args=('winner',), name='winner')

    loser.start()
    assert loser_parked.wait(timeout=_WAIT_TIMEOUT), 'loser never reached the write path'
    winner.start()
    winner.join(timeout=_WAIT_TIMEOUT)
    winner_committed.set()
    loser.join(timeout=_WAIT_TIMEOUT)

    assert not winner.is_alive(), 'winner thread hung'
    assert not loser.is_alive(), 'loser thread hung'

    outcomes = [results.get('winner'), results.get('loser')]

    # The core regression: neither concurrent write may crash with a 500 /
    # IntegrityError.
    assert not any(_is_server_error(o) for o in outcomes), results

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
