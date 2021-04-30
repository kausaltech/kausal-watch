import pytest
from datetime import date
from django.core.exceptions import ValidationError

from indicators.tests.factories import IndicatorFactory, IndicatorValueFactory

pytestmark = pytest.mark.django_db


def test_indicator_updated_values_due_at_too_early():
    indicator = IndicatorFactory()
    assert indicator.updated_values_due_at is None
    value = IndicatorValueFactory(indicator=indicator, date=date(2020, 12, 31))
    indicator.handle_values_update()
    assert indicator.latest_value == value
    # Try to set a due date so that there is already a value within the previous year
    indicator.updated_values_due_at = date(2021, 3, 1)
    with pytest.raises(ValidationError):
        indicator.full_clean()


@pytest.mark.parametrize('time_resolution,should_raise', [
    ('year', False),
    ('month', True),
    ('week', True),
    ('day', True),
])
def test_indicator_updated_values_due_at_resolution(time_resolution, should_raise):
    indicator = IndicatorFactory(time_resolution=time_resolution, updated_values_due_at=date(2020, 1, 1))
    if should_raise:
        with pytest.raises(ValidationError):
            indicator.full_clean()
    else:
        indicator.full_clean()
