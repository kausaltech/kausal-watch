import pytest
from datetime import date, timedelta

from indicators.tests.factories import IndicatorFactory, IndicatorValueFactory

pytestmark = pytest.mark.django_db


def test_indicator_can_be_saved():
    IndicatorFactory()


def test_add_first_value_updates_indicator_latest_value():
    indicator = IndicatorFactory()
    assert not indicator.values.exists()
    assert indicator.latest_value is None
    value = IndicatorValueFactory(indicator=indicator)
    indicator.refresh_from_db()
    assert indicator.latest_value == value


def test_add_value_updates_indicator_latest_value():
    indicator = IndicatorFactory()
    old_value = IndicatorValueFactory(indicator=indicator)
    assert indicator.latest_value == old_value
    new_date = indicator.latest_value.date + timedelta(days=1)
    new_value = IndicatorValueFactory(indicator=indicator, date=new_date)
    indicator.refresh_from_db()
    assert indicator.latest_value == new_value


def test_add_value_keeps_null_due_date():
    indicator = IndicatorFactory()
    assert indicator.updated_values_due_at is None
    IndicatorValueFactory(indicator=indicator)
    indicator.refresh_from_db()
    assert indicator.updated_values_due_at is None


def test_add_value_updates_non_null_due_date():
    indicator = IndicatorFactory(updated_values_due_at=date(2020, 1, 1))
    IndicatorValueFactory(indicator=indicator, date=date(2020, 1, 1))
    indicator.refresh_from_db()
    assert indicator.updated_values_due_at > date(2020, 1, 1)
