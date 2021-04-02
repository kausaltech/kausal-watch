import pytest

from indicators.tests.factories import IndicatorFactory

pytestmark = pytest.mark.django_db


def test_indicator_can_be_saved():
    IndicatorFactory()
