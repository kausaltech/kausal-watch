"""Report values are formatted for the public site's report comparison (plan 3)."""

from __future__ import annotations

import datetime

from django.utils import translation

import pytest

from reports.report_formatters import format_report_value_html


@pytest.mark.parametrize('value', [None, ''])
def test_empty_values_have_no_formatted_value(value):
    assert format_report_value_html(value) is None


@pytest.mark.parametrize(
    ('value', 'expected'),
    [
        (True, 'Yes'),
        (False, 'No'),
        (datetime.date(2025, 2, 1), 'Feb. 1, 2025'),
        (2.5, '2.5'),
        ('Fish & chips <b>', 'Fish &amp; chips &lt;b&gt;'),
    ],
)
def test_values_are_formatted_as_escaped_text(value, expected):
    with translation.override('en-us'):
        assert format_report_value_html(value) == expected
