from __future__ import annotations

import json

from wagtail.admin.rich_text import get_rich_text_editor_widget

import pytest


@pytest.fixture
def widget():
    return get_rich_text_editor_widget('default')


def test_format_value_normalizes_bare_void_tag(widget) -> None:
    # A bare <br> crashes the stock converter; the widget must sanitize it on read.
    result = widget.format_value('<p>a<br>b</p>')
    assert isinstance(result, str)
    json.loads(result)  # valid contentstate JSON


def test_format_value_degrades_on_irreparable_markup(widget, monkeypatch) -> None:
    captured: list[BaseException] = []
    monkeypatch.setattr(
        'admin_site.draftail_rich_text_area.capture_exception',
        captured.append,
    )
    # Crossed tags cannot be fixed by void-tag normalization.
    result = widget.format_value('<p><em>crossed</p></em>')
    assert isinstance(result, str)
    json.loads(result)
    assert captured, 'irreparable markup should be reported to Sentry'
    assert 'crossed' in result  # text content survives the degrade


def test_format_value_passes_through_healthy_and_empty(widget) -> None:
    assert isinstance(widget.format_value('<p>hi</p>'), str)
    # None and '' must not raise.
    widget.format_value('')
    widget.format_value(None)
