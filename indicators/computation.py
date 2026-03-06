from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kausal_common.datasets.models import DatasetMetric, DimensionCategory

from indicators.models.computation import DatasetMetricComputation

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import date
    from decimal import Decimal

    from kausal_common.datasets.models import Dataset


@dataclass
class ComputedValue:
    """A computed metric value with resolved ORM instances, ready for serialization."""

    date: date
    value: Decimal | None
    metric: DatasetMetric
    dimension_categories: list[DimensionCategory]


def _apply_op(op: str, a: Decimal | None, b: Decimal | None) -> Decimal | None:
    if a is None or b is None:
        return None
    match op:
        case 'multiply':
            return a * b
        case 'divide':
            return a / b if b != 0 else None
        case 'add':
            return a + b
        case 'subtract':
            return a - b
        case _:
            raise ValueError(f'Unknown operation: {op}')


def _compute_metric_values(
    values: dict[tuple[date, frozenset[int], int], Decimal | None],
    computations: Sequence[DatasetMetricComputation],
) -> list[tuple[date, frozenset[int], int, Decimal | None]]:
    """
    Apply computation definitions and return raw computed tuples.

    ``values`` is a lookup of (date, dimension_category_ids, metric_id) -> value,
    built by the caller from DataPoints, IndicatorGoalDataPoints, or any source.

    Computations are applied in order, so earlier results can feed later ones.
    """
    results: list[tuple[date, frozenset[int], int, Decimal | None]] = []

    for comp in computations:
        keys = {
            (d, dims)
            for d, dims, m in values
            if m in (comp.operand_a_id, comp.operand_b_id)
        }
        for d, dims in sorted(keys):
            a = values.get((d, dims, comp.operand_a_id))
            b = values.get((d, dims, comp.operand_b_id))
            result = _apply_op(comp.operation, a, b)
            values[(d, dims, comp.target_metric_id)] = result
            results.append((d, dims, comp.target_metric_id, result))

    return results


def compute_dataset_values(dataset: Dataset) -> list[ComputedValue]:
    """
    Compute metric values for a dataset.

    Fetches data points, applies computations, and returns resolved
    ComputedValue instances.
    """
    computations = list(
        DatasetMetricComputation.objects.filter(schema=dataset.schema).select_related(
            'target_metric', 'operand_a', 'operand_b',
        )
    )
    if not computations:
        return []

    data_points = dataset.data_points.prefetch_related('dimension_categories').all()  # type: ignore[attr-defined]
    values: dict[tuple[date, frozenset[int], int], Decimal | None] = {}
    for dp in data_points:
        dim_cat_ids = frozenset(dc.id for dc in dp.dimension_categories.all())
        values[(dp.date, dim_cat_ids, dp.metric_id)] = dp.value

    raw = _compute_metric_values(values, computations)
    if not raw:
        return []

    # Bulk-fetch referenced metrics and dimension categories
    metric_ids = {r[2] for r in raw}
    all_dim_cat_ids: set[int] = set()
    for _, dims, _, _ in raw:
        all_dim_cat_ids |= dims

    metrics_by_id = {m.id: m for m in DatasetMetric.objects.filter(id__in=metric_ids)}
    dim_cats_by_id = (
        {dc.id: dc for dc in DimensionCategory.objects.filter(id__in=all_dim_cat_ids)}
        if all_dim_cat_ids
        else {}
    )

    return [
        ComputedValue(
            date=d,
            value=val,
            metric=metrics_by_id[metric_id],
            dimension_categories=[dim_cats_by_id[dc_id] for dc_id in sorted(dims)],
        )
        for d, dims, metric_id, val in raw
    ]
