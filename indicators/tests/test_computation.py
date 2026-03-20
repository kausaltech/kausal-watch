from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType

import pytest

from kausal_common.datasets.computation import _apply_op, compute_dataset_values, compute_for_queryset
from kausal_common.datasets.models import DataPoint, Dataset, DatasetMetric, DatasetMetricComputation, DatasetSchema

from indicators.models.goal_data_point import IndicatorGoalDataPoint
from indicators.tests.factories import IndicatorFactory, IndicatorValueFactory

pytestmark = pytest.mark.django_db


def compute_dataset_goal_values(dataset):
    return compute_for_queryset(dataset, dataset.goal_data_points.all())


@pytest.mark.parametrize(
    ('op', 'a', 'b', 'expected'),
    [
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
    ],
)
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

    def test_missing_operand_returns_no_result(self):
        dataset, metric_a, _metric_b, _target = _create_schema_with_computation('add')
        d = datetime.date(2024, 1, 1)
        DataPoint.objects.create(dataset=dataset, metric=metric_a, date=d, value=Decimal(5))

        results = compute_dataset_values(dataset)

        assert results == []

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
            dataset=dataset,
            metric=metric,
            date=datetime.date(2030, 1, 1),
            value=Decimal(10),
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

        assert actual_results == []  # metric_b missing from actuals
        assert goal_results == []  # metric_a missing from goals


def _create_null_operand_setup(indicator, operation='multiply'):
    """
    Create a computation with operand_a=NULL (indicator's own values as input).

    Returns (dataset, factor_metric, target_metric).
    """
    schema = DatasetSchema.objects.create(name='Indicator Schema')
    factor = DatasetMetric.objects.create(schema=schema, label='Emission factor', unit='tCO2e')
    target = DatasetMetric.objects.create(schema=schema, label='Total emissions', unit='tCO2e')
    DatasetMetricComputation.objects.create(
        schema=schema,
        target_metric=target,
        operation=operation,
        operand_a=None,
        operand_b=factor,
    )
    indicator_ct = ContentType.objects.get_for_model(type(indicator))
    dataset = Dataset.objects.create(
        schema=schema,
        scope_content_type=indicator_ct,
        scope_id=indicator.pk,
    )
    return dataset, factor, target


class TestNullOperandComputation:
    """Tests for NULL operand_a (virtual indicator values)."""

    def test_null_operand_multiply(self):
        """NULL operand_a resolves indicator values and multiplies with factor."""
        indicator = IndicatorFactory.create()
        d = datetime.date(2024, 1, 1)
        IndicatorValueFactory.create(indicator=indicator, date=d, value=100.0)

        dataset, factor, target = _create_null_operand_setup(indicator)
        DataPoint.objects.create(dataset=dataset, metric=factor, date=d, value=Decimal('0.5'))

        results = compute_dataset_values(dataset)

        assert len(results) == 1
        assert results[0].date == d
        assert results[0].value == Decimal('50.0')
        assert results[0].metric == target

    def test_null_operand_multiple_dates(self):
        """NULL operand_a works across multiple dates."""
        indicator = IndicatorFactory.create()
        d1 = datetime.date(2024, 1, 1)
        d2 = datetime.date(2025, 1, 1)
        IndicatorValueFactory.create(indicator=indicator, date=d1, value=100.0)
        IndicatorValueFactory.create(indicator=indicator, date=d2, value=200.0)

        dataset, factor, _target = _create_null_operand_setup(indicator)
        DataPoint.objects.create(dataset=dataset, metric=factor, date=d1, value=Decimal('0.5'))
        DataPoint.objects.create(dataset=dataset, metric=factor, date=d2, value=Decimal('0.3'))

        results = compute_dataset_values(dataset)

        assert len(results) == 2
        values_by_date = {r.date: r.value for r in results}
        assert values_by_date[d1] == Decimal('50.0')
        assert values_by_date[d2] == Decimal('60.0')

    def test_null_operand_missing_factor_value(self):
        """When factor DataPoint is missing for a date, no result is produced for that date."""
        indicator = IndicatorFactory.create()
        d = datetime.date(2024, 1, 1)
        IndicatorValueFactory.create(indicator=indicator, date=d, value=100.0)

        dataset, _factor, _target = _create_null_operand_setup(indicator)
        # No DataPoint created for the factor

        results = compute_dataset_values(dataset)

        # No result because factor value is missing (no key match)
        assert len(results) == 0

    def test_null_operand_missing_indicator_value(self):
        """When indicator has no value for a date, no result is produced."""
        indicator = IndicatorFactory.create()
        d = datetime.date(2024, 1, 1)
        # No IndicatorValue for this date

        dataset, factor, _target = _create_null_operand_setup(indicator)
        DataPoint.objects.create(dataset=dataset, metric=factor, date=d, value=Decimal('0.5'))

        results = compute_dataset_values(dataset)

        assert len(results) == 0

    def test_null_operand_with_regular_computation(self):
        """NULL operand can coexist with regular (non-null) computations."""
        indicator = IndicatorFactory.create()
        d = datetime.date(2024, 1, 1)
        IndicatorValueFactory.create(indicator=indicator, date=d, value=100.0)

        schema = DatasetSchema.objects.create(name='Mixed Schema')
        # Factor for null operand computation
        factor = DatasetMetric.objects.create(schema=schema, label='Factor')
        result1 = DatasetMetric.objects.create(schema=schema, label='Result 1')
        # Metrics for regular computation
        metric_a = DatasetMetric.objects.create(schema=schema, label='Metric A')
        metric_b = DatasetMetric.objects.create(schema=schema, label='Metric B')
        result2 = DatasetMetric.objects.create(schema=schema, label='Result 2')

        # Null operand computation: indicator_values * factor = result1
        DatasetMetricComputation.objects.create(
            schema=schema, target_metric=result1, operation='multiply',
            operand_a=None, operand_b=factor,
        )
        # Regular computation: metric_a + metric_b = result2
        DatasetMetricComputation.objects.create(
            schema=schema, target_metric=result2, operation='add',
            operand_a=metric_a, operand_b=metric_b,
        )

        indicator_ct = ContentType.objects.get_for_model(type(indicator))
        dataset = Dataset.objects.create(
            schema=schema,
            scope_content_type=indicator_ct,
            scope_id=indicator.pk,
        )
        DataPoint.objects.create(dataset=dataset, metric=factor, date=d, value=Decimal(2))
        DataPoint.objects.create(dataset=dataset, metric=metric_a, date=d, value=Decimal(10))
        DataPoint.objects.create(dataset=dataset, metric=metric_b, date=d, value=Decimal(20))

        results = compute_dataset_values(dataset)

        results_by_metric = {r.metric.id: r for r in results}
        assert results_by_metric[result1.id].value == Decimal('200.0')  # 100 * 2
        assert results_by_metric[result2.id].value == Decimal(30)  # 10 + 20

    def test_null_operand_no_indicator_scope(self):
        """Dataset not scoped to an indicator returns no virtual values."""
        schema = DatasetSchema.objects.create(name='No Scope Schema')
        factor = DatasetMetric.objects.create(schema=schema, label='Factor')
        target = DatasetMetric.objects.create(schema=schema, label='Target')
        DatasetMetricComputation.objects.create(
            schema=schema, target_metric=target, operation='multiply',
            operand_a=None, operand_b=factor,
        )
        dataset = Dataset.objects.create(schema=schema)
        d = datetime.date(2024, 1, 1)
        DataPoint.objects.create(dataset=dataset, metric=factor, date=d, value=Decimal(5))

        results = compute_dataset_values(dataset)

        # No indicator values to resolve, so no results
        assert len(results) == 0
