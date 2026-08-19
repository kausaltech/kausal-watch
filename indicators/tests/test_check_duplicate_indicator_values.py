from __future__ import annotations

from datetime import date
from io import StringIO

from django.core.management import call_command

import pytest

from indicators.tests.factories import (
    DimensionCategoryFactory,
    DimensionFactory,
    IndicatorDimensionFactory,
    IndicatorFactory,
    IndicatorValueFactory,
)

pytestmark = pytest.mark.django_db


def run_command(*args) -> str:
    out = StringIO()
    call_command('check_duplicate_indicator_values', *args, stdout=out)
    return out.getvalue()


def test_reports_nothing_when_data_is_clean(plan):
    indicator = IndicatorFactory.create(plans=[plan])
    IndicatorValueFactory.create(indicator=indicator, date=date(2019, 12, 31))
    IndicatorValueFactory.create(indicator=indicator, date=date(2020, 12, 31))

    output = run_command()

    assert str(indicator.pk) not in output
    assert 'No duplicate' in output


def test_several_categories_on_one_date_are_not_duplicates(plan):
    indicator = IndicatorFactory.create(plans=[plan])
    dimension = DimensionFactory.create()
    first, second = DimensionCategoryFactory.create_batch(2, dimension=dimension)
    IndicatorDimensionFactory.create(indicator=indicator, dimension=dimension)
    IndicatorValueFactory.create(indicator=indicator, date=date(2019, 12, 31))
    IndicatorValueFactory.create(indicator=indicator, date=date(2019, 12, 31), categories=[first])
    IndicatorValueFactory.create(indicator=indicator, date=date(2019, 12, 31), categories=[second])

    output = run_command()

    assert 'No duplicate' in output


def test_reports_duplicate_uncategorized_values(plan):
    indicator = IndicatorFactory.create(plans=[plan])
    values = [IndicatorValueFactory.create(indicator=indicator, date=date(2019, 12, 31)) for _ in range(2)]

    output = run_command()

    assert f'indicator {indicator.pk}' in output
    assert '2019-12-31' in output
    for value in values:
        assert str(value.pk) in output


def test_reports_duplicate_categorized_values(plan):
    indicator = IndicatorFactory.create(plans=[plan])
    dimension = DimensionFactory.create()
    category = DimensionCategoryFactory.create(dimension=dimension)
    IndicatorDimensionFactory.create(indicator=indicator, dimension=dimension)
    IndicatorValueFactory.create(indicator=indicator, date=date(2019, 12, 31))
    for _ in range(2):
        IndicatorValueFactory.create(indicator=indicator, date=date(2019, 12, 31), categories=[category])

    output = run_command()

    assert f'indicator {indicator.pk}' in output
    assert str(category.pk) in output


def test_plan_option_limits_the_scan(plan, plan_factory):
    other_plan = plan_factory()
    indicator = IndicatorFactory.create(plans=[other_plan])
    IndicatorValueFactory.create_batch(2, indicator=indicator, date=date(2019, 12, 31))

    assert f'indicator {indicator.pk}' in run_command('--plan', other_plan.identifier)
    assert 'No duplicate' in run_command('--plan', plan.identifier)
