from __future__ import annotations

import subprocess
from unittest.mock import patch

import pytest

from notifications.mjml import render_mjml


def test_compiler_failure_is_raised():
    failure = subprocess.CalledProcessError(1, 'mjml', stderr='invalid markup')
    with patch('notifications.mjml.subprocess.run', side_effect=failure), pytest.raises(subprocess.CalledProcessError):
        render_mjml('<mjml></mjml>')
