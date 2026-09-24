"""
Tests for the rules that move each plan onto `Plan.visibility`.

The migration is where this change can go wrong quietly: it decides, once, what every existing
plan is allowed to show the public, and it runs before anyone can look. The rules are exercised
here as a pure function so they can be read next to the old behaviour they replace, without
needing the historical models they are applied to.
"""

from __future__ import annotations

import importlib
from datetime import UTC, datetime, timedelta

from django.db import connection

import pytest

from kausal_common.testing.utils import parse_table

# The module name starts with a digit, so it cannot be imported by name. The rules deliberately
# live inside the migration rather than in app code, which is free to change underneath it.
decide_visibility = importlib.import_module('actions.migrations.0193_plan_visibility').decide_visibility

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
PAST = NOW - timedelta(days=1)
FUTURE = NOW + timedelta(days=1)

# `published` is the old publication date; `exposed` is the old
# `expose_unpublished_plan_only_to_authenticated_user`, which hid an unpublished plan when true;
# `override` says one of the plan's domains had `publication_status_override` forced to published.
# `unscheduled` says the publication date is cleared as well.
MAPPING = """
    published  exposed  override  visibility  unscheduled
    past       +        -         public      -
    past       -        -         public      -
    none       -        -         public      -           # the flag off meant anyone could read it
    none       +        -         internal    -
    future     +        -         internal    +           # scheduled: unscheduled rather than exposed early
    future     -        -         public      -           # already readable, so it keeps its launch date
    none       +        +         public      -           # the overridden domain served it to anyone
    future     +        +         public      -           # likewise, and its other domains launch on schedule
"""

DATES = {'past': PAST, 'future': FUTURE, 'none': None}


@pytest.mark.parametrize(*parse_table(MAPPING))
def test_the_old_rules_map_onto_visibility(published, exposed, override, visibility, unscheduled):
    assert decide_visibility(DATES[published], exposed, override, NOW) == (visibility, unscheduled)


def test_a_plan_published_exactly_now_counts_as_published():
    """The old rule was `published_at <= now`, so the boundary belongs to the published side."""
    assert decide_visibility(NOW, exposed_only_to_authenticated=True, has_published_override=False, now=NOW) == ('public', False)


def test_a_scheduled_plan_is_never_made_public_early():
    """
    Guard the point of this finding.

    Marking a future date public would expose the plan's data before the day it was scheduled
    for, through every path that carries no hostname. This only applies when the flag hid the
    plan; with the flag off, its data was readable before the date anyway.
    """
    visibility, _ = decide_visibility(FUTURE, exposed_only_to_authenticated=True, has_published_override=False, now=NOW)
    assert visibility == 'internal'


@pytest.mark.django_db
def test_a_row_this_release_writes_hides_an_unpublished_plan_from_the_previous_one(plan_factory):
    """
    Keep the retired column safe for the release that still reads it.

    This release no longer knows the field, so it omits the column when it creates a
    `PlanFeatures` row. The previous release's pods, still running during a rollout or back after
    a rollback, read the column as the answer to whether an unpublished plan is hidden from
    anonymous visitors — so whatever the database fills in must be the answer that hides it.
    """
    plan = plan_factory()
    with connection.cursor() as cursor:
        cursor.execute(
            'SELECT expose_unpublished_plan_only_to_authenticated_user FROM actions_planfeatures WHERE plan_id = %s',
            [plan.pk],
        )
        (exposed_only_to_authenticated,) = cursor.fetchone()
    assert exposed_only_to_authenticated is True
