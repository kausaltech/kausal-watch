from datetime import date

from django.core.exceptions import ValidationError

import pytest

from indicators.tests.factories import IndicatorFactory, IndicatorValueFactory

pytestmark = pytest.mark.django_db


def test_indicator_updated_values_due_at_too_early():
    indicator = IndicatorFactory.create()
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
    indicator = IndicatorFactory.create(time_resolution=time_resolution, updated_values_due_at=date(2020, 1, 1))
    if should_raise:
        with pytest.raises(ValidationError):
            indicator.full_clean()
    else:
        indicator.full_clean()


def test_indicator_plans_with_access_include_plans_with_same_organization(plan):
    indicator = IndicatorFactory.create(organization=plan.organization)
    assert plan in indicator.get_plans_with_access()
    assert plan not in indicator.plans.all()


def test_indicator_plans_with_access_dont_include_other_plans(plan):
    indicator = IndicatorFactory.create()
    assert plan not in indicator.get_plans_with_access()
    assert plan not in indicator.plans.all()


def test_indicator_plans_with_access_includes_indicator_plan(plan, indicator):
    indicator.plans.add(plan)
    assert plan in indicator.get_plans_with_access()


def test_indicator_handle_values_update_bumps_deadline_multiple_times():
    """
    Test that handle_values_update() bumps updated_values_due_at multiple times if needed.

    This covers the edge case where an indicator has an old deadline that's far behind the
    latest value date. A single 1-year bump isn't sufficient to pass the validation in clean().

    Fixes WATCH-BACKEND-3E4.
    """
    # Create indicator with a deadline that's way in the past
    indicator = IndicatorFactory.create(updated_values_due_at=date(2023, 6, 1))

    # Add a value for a much later date
    value = IndicatorValueFactory(indicator=indicator, date=date(2025, 12, 31))

    # Before handle_values_update, the deadline is way too early
    # (2023-06-01 is more than 1 year before 2025-12-31)
    assert indicator.updated_values_due_at == date(2023, 6, 1)

    # Call handle_values_update - this should bump the deadline enough times
    # so that it's more than 1 year after the latest value
    indicator.handle_values_update()

    # Verify latest_value was updated
    assert indicator.latest_value == value

    # The deadline should have been bumped to be > latest_value.date + 1 year
    # 2025-12-31 + 1 year = 2026-12-31, so deadline should be > 2026-12-31
    # Starting from 2023-06-01:
    # +1 year = 2024-06-01 (still <= 2026-12-31)
    # +1 year = 2025-06-01 (still <= 2026-12-31)
    # +1 year = 2026-06-01 (still <= 2026-12-31)
    # +1 year = 2027-06-01 (> 2026-12-31) ✓
    assert indicator.updated_values_due_at == date(2027, 6, 1)

    # Verify that full_clean passes (no ValidationError)
    indicator.full_clean()
