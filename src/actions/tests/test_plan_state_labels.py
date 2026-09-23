"""The two axes must not share a word in any language we ship."""

from __future__ import annotations

from django.utils import translation

import pytest

from aplans.utils import RestrictedVisibilityModel

from actions.models import Plan


@pytest.mark.parametrize('language', ['en', 'fi', 'de', 'sv'])
def test_launch_and_visibility_labels_never_collide(language):
    with translation.override(language):
        launch = {str(s.label) for s in Plan.LiveState}
        visibility = {str(s.label) for s in RestrictedVisibilityModel.VisibilityState}
        assert not (launch & visibility), f'{language}: {launch & visibility}'
