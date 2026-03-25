"""
Configure the kausal_common.datasets app.

There is some project-specific configration required for the reusable datasets apps
found in kausal_common.datasets to make it adapt to different use cases in Watch
and Paths. The configuration must be found in the module
dataset_config under the project directory.
"""

from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date
    from decimal import Decimal

    from django.db.models import Model

    from kausal_common.datasets.models import Dataset

    from aplans.types import WatchAdminRequest

    from indicators.models import Indicator


def schema_default_scope():
    # Only call in view contexts where the context has been initialized
    from aplans.context_vars import ctx_request

    request = typing.cast('WatchAdminRequest', ctx_request.get())
    return request.get_active_admin_plan()


def validate_unit(unit: str) -> None:
    """No-op in Watch — unit field allows free-text entry."""


def _resolve_indicator_for_dataset(dataset: Dataset) -> Indicator | None:
    """Return the Indicator scoped to this dataset, or None."""
    from django.contrib.contenttypes.models import ContentType

    from indicators.models import Indicator

    indicator_ct = ContentType.objects.get_for_model(Indicator)
    if dataset.scope_content_type_id != indicator_ct.pk:
        return None
    if dataset.scope_id is None:
        return None
    try:
        return Indicator.objects.select_related('unit').get(pk=dataset.scope_id)
    except Indicator.DoesNotExist:
        return None


def _schema_has_null_operand(dataset: Dataset) -> bool:
    from kausal_common.datasets.models import DatasetMetricComputation

    return DatasetMetricComputation.objects.filter(
        schema=dataset.schema,
        operand_a__isnull=True,
    ).exists()


def get_virtual_metrics_for_schema(dataset: Dataset) -> list[dict]:
    """
    Return virtual metric dicts to prepend to the schema response.

    Called by DatasetSchemaSerializer when a dataset with null-operand
    computations is loaded.
    """
    if not _schema_has_null_operand(dataset):
        return []
    indicator = _resolve_indicator_for_dataset(dataset)
    if indicator is None:
        return []

    from kausal_common.datasets.computation import get_indicator_virtual_metric_uuid

    virtual_uuid = str(get_indicator_virtual_metric_uuid(indicator.pk))
    unit_label = indicator.unit.name_i18n if indicator.unit else ''
    return [
        {
            'uuid': virtual_uuid,
            'schema': str(dataset.schema.uuid),  # type: ignore[union-attr]
            'label': indicator.name_i18n,
            'unit': unit_label,
            'order': -1,
            'is_computed': False,
            'is_virtual': True,
            'computed_by': None,
        }
    ]


def get_virtual_metric_data(dataset: Dataset) -> list[dict]:
    """
    Return data points for virtual metrics (indicator values shaped as data-point dicts).

    Synthetic UUIDs are deterministic so they're stable across requests.
    """
    if not _schema_has_null_operand(dataset):
        return []
    indicator = _resolve_indicator_for_dataset(dataset)
    if indicator is None:
        return []

    from kausal_common.datasets.computation import (
        get_indicator_virtual_datapoint_uuid,
        get_indicator_virtual_metric_uuid,
    )

    virtual_metric_uuid = str(get_indicator_virtual_metric_uuid(indicator.pk))
    results: list[dict] = []
    for iv in indicator.values.prefetch_related('categories').all():
        dim_cat_uuids_str = '.'.join(sorted(str(dc.uuid) for dc in iv.categories.all() if hasattr(dc, 'uuid')))
        dp_uuid = str(
            get_indicator_virtual_datapoint_uuid(
                indicator.pk,
                iv.date.isoformat(),
                dim_cat_uuids_str,
            )
        )
        results.append({
            'uuid': dp_uuid,
            'dataset': str(dataset.uuid) if dataset.uuid else None,
            'date': iv.date.isoformat(),
            'value': iv.value,
            'metric': virtual_metric_uuid,
            'dimension_categories': [],
        })
    return results


def resolve_null_operand_values(
    dataset: Dataset,
) -> dict[tuple[date, frozenset[int]], Decimal | None]:
    """
    Resolve indicator values as virtual metric-0 input for NULL operand_a computations.

    When a DatasetMetricComputation has operand_a=NULL, the indicator's own
    IndicatorValue rows serve as the input. This function fetches those values
    and returns them keyed by (date, dimension_category_ids).
    """
    from decimal import Decimal as _Decimal

    indicator = _resolve_indicator_for_dataset(dataset)
    if indicator is None:
        return {}

    from kausal_common.datasets.models import DatasetSchema

    time_res = dataset.schema.time_resolution if dataset.schema else None

    def _normalize_date(d: date) -> date:
        if time_res == DatasetSchema.TimeResolution.YEARLY:
            return d.replace(month=1, day=1)
        if time_res == DatasetSchema.TimeResolution.MONTHLY:
            return d.replace(day=1)
        return d

    values: dict[tuple[date, frozenset[int]], Decimal | None] = {}
    for iv in indicator.values.prefetch_related('categories').all():
        dim_cat_ids = frozenset(dc.id for dc in iv.categories.all())
        values[(_normalize_date(iv.date), dim_cat_ids)] = _Decimal(str(iv.value)) if iv.value is not None else None
    return values


DATA_SOURCE_DEFAULT_SCOPE_CONTENT_TYPE = ('actions', 'plan')
SCHEMA_HAS_SINGLE_DATASET: bool = False
SCHEMA_DEFAULT_SCOPE_FUNCTION: Callable[[], Model] | None = schema_default_scope
# Permission policies for datasets
SHOW_DATASETS_IN_MENU: bool = False
SHOW_SCHEMAS_IN_MENU: bool = False
SCHEMA_PERMISSION_POLICY = 'datasets.permission_policy.DatasetSchemaPermissionPolicy'
DATASET_PERMISSION_POLICY = 'datasets.permission_policy.ScopeInheritedDatasetPermissionPolicy'
DATA_POINT_PERMISSION_POLICY = 'datasets.permission_policy.DataPointPermissionPolicy'
DATA_SOURCE_PERMISSION_POLICY = 'datasets.permission_policy.DataSourcePermissionPolicy'
