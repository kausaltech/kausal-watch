from __future__ import annotations

import datetime
from decimal import Decimal

import pytest

from kausal_common.datasets.models import DataPoint, Dataset, DatasetMetric, DatasetSchema

from indicators.computation import _apply_op, compute_dataset_goal_values, compute_dataset_values
from indicators.models.computation import DatasetMetricComputation
from indicators.models.goal_data_point import IndicatorGoalDataPoint

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(('op', 'a', 'b', 'expected'), [
    ('multiply', Decimal(3), Decimal(5), Decimal(15)),
    ('multiply', Decimal(0), Decimal(5), Decimal(0)),
    ('multiply', Decimal(-2), Decimal(3), Decimal(-6)),
    ('divide', Decimal(10), Decimal(2), Decimal(5)),
    ('divide', Decimal(7), Decimal(3), Decimal(7) / Decimal(3)),
    ('divide', Decimal(10), Decimal(0), None),
    ('add', Decimal(3), Decimal(5), Decimal(8)),
    ('add', Decimal(-3), Decimal(5), Decimal(2)),
    ('subtract', Decimal(10), Decimal(3), Decimal(7)),
    ('subtract', Decimal(3), Decimal(10), Decimal(-7)),
])
def test_apply_op(op, a, b, expected):
    assert _apply_op(op, a, b) == expected


@pytest.mark.parametrize('op', ['multiply', 'divide', 'add', 'subtract'])
def test_apply_op_none_operand_a(op):
    assert _apply_op(op, None, Decimal(5)) is None


@pytest.mark.parametrize('op', ['multiply', 'divide', 'add', 'subtract'])
def test_apply_op_none_operand_b(op):
    assert _apply_op(op, Decimal(5), None) is None


@pytest.mark.parametrize('op', ['multiply', 'divide', 'add', 'subtract'])
def test_apply_op_both_none(op):
    assert _apply_op(op, None, None) is None


def test_apply_op_unknown_operation():
    with pytest.raises(ValueError, match='Unknown operation'):
        _apply_op('modulo', Decimal(5), Decimal(3))


def _create_schema_with_computation(operation='multiply'):
    """Create a schema with two input metrics, one target metric, and a computation."""
    schema = DatasetSchema.objects.create(name='Test Schema')
    metric_a = DatasetMetric.objects.create(schema=schema, label='Metric A')
    metric_b = DatasetMetric.objects.create(schema=schema, label='Metric B')
    target = DatasetMetric.objects.create(schema=schema, label='Target')
    DatasetMetricComputation.objects.create(
        schema=schema,
        target_metric=target,
        operation=operation,
        operand_a=metric_a,
        operand_b=metric_b,
    )
    dataset = Dataset.objects.create(schema=schema)
    return dataset, metric_a, metric_b, target


class TestComputeDatasetValues:
    def test_multiply(self):
        dataset, metric_a, metric_b, target = _create_schema_with_computation('multiply')
        d = datetime.date(2024, 1, 1)
        DataPoint.objects.create(dataset=dataset, metric=metric_a, date=d, value=Decimal(6))
        DataPoint.objects.create(dataset=dataset, metric=metric_b, date=d, value=Decimal(7))

        results = compute_dataset_values(dataset)

        assert len(results) == 1
        assert results[0].date == d
        assert results[0].value == Decimal(42)
        assert results[0].metric == target
        assert results[0].dimension_categories == []

    def test_divide(self):
        dataset, metric_a, metric_b, _target = _create_schema_with_computation('divide')
        d = datetime.date(2024, 1, 1)
        DataPoint.objects.create(dataset=dataset, metric=metric_a, date=d, value=Decimal(10))
        DataPoint.objects.create(dataset=dataset, metric=metric_b, date=d, value=Decimal(4))

        results = compute_dataset_values(dataset)

        assert len(results) == 1
        assert results[0].value == Decimal('2.5')

    def test_no_computations_returns_empty(self):
        schema = DatasetSchema.objects.create(name='Empty')
        metric = DatasetMetric.objects.create(schema=schema, label='M')
        dataset = Dataset.objects.create(schema=schema)
        DataPoint.objects.create(dataset=dataset, metric=metric, date=datetime.date(2024, 1, 1))

        assert compute_dataset_values(dataset) == []

    def test_missing_operand_returns_none_value(self):
        dataset, metric_a, _metric_b, _target = _create_schema_with_computation('add')
        d = datetime.date(2024, 1, 1)
        DataPoint.objects.create(dataset=dataset, metric=metric_a, date=d, value=Decimal(5))

        results = compute_dataset_values(dataset)

        assert len(results) == 1
        assert results[0].value is None

    def test_multiple_dates(self):
        dataset, metric_a, metric_b, _target = _create_schema_with_computation('add')
        d1 = datetime.date(2024, 1, 1)
        d2 = datetime.date(2024, 6, 1)
        DataPoint.objects.create(dataset=dataset, metric=metric_a, date=d1, value=Decimal(10))
        DataPoint.objects.create(dataset=dataset, metric=metric_b, date=d1, value=Decimal(20))
        DataPoint.objects.create(dataset=dataset, metric=metric_a, date=d2, value=Decimal(100))
        DataPoint.objects.create(dataset=dataset, metric=metric_b, date=d2, value=Decimal(200))

        results = compute_dataset_values(dataset)

        assert len(results) == 2
        values_by_date = {r.date: r.value for r in results}
        assert values_by_date[d1] == Decimal(30)
        assert values_by_date[d2] == Decimal(300)


class TestComputeDatasetGoalValues:
    def test_multiply(self):
        dataset, metric_a, metric_b, target = _create_schema_with_computation('multiply')
        d = datetime.date(2030, 1, 1)
        IndicatorGoalDataPoint.objects.create(dataset=dataset, metric=metric_a, date=d, value=Decimal(3))
        IndicatorGoalDataPoint.objects.create(dataset=dataset, metric=metric_b, date=d, value=Decimal(5))

        results = compute_dataset_goal_values(dataset)

        assert len(results) == 1
        assert results[0].date == d
        assert results[0].value == Decimal(15)
        assert results[0].metric == target
        assert results[0].dimension_categories == []

    def test_subtract(self):
        dataset, metric_a, metric_b, _target = _create_schema_with_computation('subtract')
        d = datetime.date(2030, 1, 1)
        IndicatorGoalDataPoint.objects.create(dataset=dataset, metric=metric_a, date=d, value=Decimal(100))
        IndicatorGoalDataPoint.objects.create(dataset=dataset, metric=metric_b, date=d, value=Decimal(30))

        results = compute_dataset_goal_values(dataset)

        assert len(results) == 1
        assert results[0].value == Decimal(70)

    def test_no_computations_returns_empty(self):
        schema = DatasetSchema.objects.create(name='Empty')
        metric = DatasetMetric.objects.create(schema=schema, label='M')
        dataset = Dataset.objects.create(schema=schema)
        IndicatorGoalDataPoint.objects.create(
            dataset=dataset, metric=metric, date=datetime.date(2030, 1, 1), value=Decimal(10),
        )

        assert compute_dataset_goal_values(dataset) == []

    def test_does_not_mix_actuals_and_goals(self):
        """Goal computation should ignore actual DataPoints and vice versa."""
        dataset, metric_a, metric_b, _target = _create_schema_with_computation('add')
        d = datetime.date(2024, 1, 1)

        # Create actuals only for metric_a, goals only for metric_b
        DataPoint.objects.create(dataset=dataset, metric=metric_a, date=d, value=Decimal(10))
        IndicatorGoalDataPoint.objects.create(dataset=dataset, metric=metric_b, date=d, value=Decimal(20))

        # Neither function should find both operands
        actual_results = compute_dataset_values(dataset)
        goal_results = compute_dataset_goal_values(dataset)

        assert len(actual_results) == 1
        assert actual_results[0].value is None  # metric_b missing from actuals

        assert len(goal_results) == 1
        assert goal_results[0].value is None  # metric_a missing from goals
