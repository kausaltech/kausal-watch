from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from wagtail.admin.rich_text.converters.contentstate import ContentstateConverter

import pytest

from actions.tests.factories import ActionFactory

pytestmark = pytest.mark.django_db


def _parses(html: str) -> bool:
    try:
        ContentstateConverter([]).from_database_format(html)
    except Exception:
        return False
    return True


def test_save_normalizes_bare_void_tag() -> None:
    action = ActionFactory.create(description='<p>a<br>b</p>')
    assert action.description == '<p>a<br/>b</p>'
    assert _parses(action.description)


def test_save_normalizes_translation() -> None:
    action = ActionFactory.create()
    action.i18n = {'description_en': '<p>x<br>y</p>'}
    action.save()
    assert action.i18n['description_en'] == '<p>x<br/>y</p>'


def test_clean_normalizes_description() -> None:
    # clean() is the path GraphQL/MCP writes reach via full_clean().
    action = ActionFactory.create()
    action.description = '<p>a<br>b</p>'
    action.clean()
    assert action.description == '<p>a<br/>b</p>'


def test_save_rejects_irreparable_markup() -> None:
    action = ActionFactory.create()
    action.description = '<p><em>crossed</p></em>'
    with pytest.raises(ValidationError):
        action.save()


def test_targeted_update_fields_save_skips_untouched_rich_text() -> None:
    action = ActionFactory.create(description='<p>ok</p>')
    # Put an unnormalized value in memory but save an unrelated field only.
    action.description = '<p>a<br>b</p>'
    action.name = 'Renamed'
    action.save(update_fields=['name'])
    # The in-memory description is left as-is (not in update_fields) and nothing is raised...
    assert action.description == '<p>a<br>b</p>'
    # ...and the DB keeps the original, still-valid value.
    action.refresh_from_db()
    assert action.description == '<p>ok</p>'


def test_guard_issues_no_database_queries() -> None:
    # The guard must stay pure CPU so it does not slow bulk writes down with per-row queries.
    action = ActionFactory.create(description='<p>a<br>b</p>')
    action.clean_rich_text_fields()  # warm the cached converter
    action.description = '<p>c<br>d</p>'
    with CaptureQueriesContext(connection) as ctx:
        action.clean_rich_text_fields()
    assert len(ctx.captured_queries) == 0, ctx.captured_queries
    assert action.description == '<p>c<br/>d</p>'
