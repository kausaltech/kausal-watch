from __future__ import annotations

import subprocess
from collections import defaultdict
from unittest.mock import patch

import pytest

from notifications.mjml import render_mjml


def test_compiler_failure_is_raised():
    failure = subprocess.CalledProcessError(1, 'mjml', stderr='invalid markup')
    with patch('notifications.mjml.subprocess.run', side_effect=failure), pytest.raises(subprocess.CalledProcessError):
        render_mjml('<mjml></mjml>')


def _render_base_header(site: dict) -> str:
    from notifications.mjml import make_jinja_environment

    template = make_jinja_environment().get_template('base.mjml')
    theme: defaultdict[str, str] = defaultdict(lambda: '#000000')
    return template.render(site=site, theme=theme, content_blocks={}, title='Title')


def test_base_links_site_title_to_view_url():
    out = _render_base_header({'title': 'Plan site', 'view_url': 'https://plan.example.com'})
    assert '<a href="https://plan.example.com"><strong' in out

