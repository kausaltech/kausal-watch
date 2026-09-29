from __future__ import annotations

import pytest

from notifications.models import DEFAULT_BRAND_DARK_COLOR
from notifications.tests.factories import BaseTemplateFactory

pytestmark = pytest.mark.django_db


def test_theme_uses_the_brand_dark_color():
    base = BaseTemplateFactory.create(brand_dark_color='#375962')
    assert base.get_notification_context()['theme']['brand_dark_color'] == '#375962'


def test_theme_falls_back_to_the_default_color_when_none_is_set():
    # A blank color would leave the header and buttons without a background.
    base = BaseTemplateFactory.create(brand_dark_color='')
    assert base.get_notification_context()['theme']['brand_dark_color'] == DEFAULT_BRAND_DARK_COLOR
