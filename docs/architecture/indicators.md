# Indicator Data Architecture

## Overview

Indicators in Kausal Watch measure progress toward climate goals. Each indicator tracks a time series of numeric values — historically stored as simple `IndicatorValue` rows with a single float per (date, dimension-category combination).

A new requirement is emerging: **indicators with multiple metrics per data point** and **computed columns**. For example, a refrigerant replacement indicator might track:

| Year | Units replaced | Emission factor (tCO2/unit) | Total emissions saved (tCO2) | Cost per unit (€/unit) | Total cost (€) |
|------|---------------:|----------------------------:|-----------------------------:|-----------------------:|---------------:|
| 2024 | 150            | 1.2                         | *180*                        | 500                    | *75 000*       |
| 2025 | 200            | 1.2                         | *240*                        | 480                    | *96 000*       |

The italic values are computed: `units × factor → total`. All of these metrics belong to the same logical indicator.

## Current State: Two Data Systems

### Legacy indicator values (`indicators/`)

- `IndicatorValue` — a single `float` per (indicator, date, dimension-categories)
- `IndicatorGoal` — a single `float` per (indicator, date)
- `indicators.Dimension` / `DimensionCategory` — classification axes for slicing indicator values
- `indicators.Dataset` — unrelated to actual data storage; purely source metadata (name, URL, license)

This system works well for single-metric time series but cannot represent multiple columns per indicator.

### Dataset system (`kausal_common/datasets/`)

A general-purpose tabular data model, shared between Kausal Watch and Kausal Paths:

- `DatasetSchema` — defines the shape of a table: time resolution, ordered metrics (columns), and dimensions. Scoped via GenericFK to a context object (in Watch: currently Plan or CategoryType).
- `DatasetMetric` — one column in the table, with a label, unit, and internal name.
- `DatasetSchemaDimension` — links a `Dimension` to a schema, giving the table categorical axes.
- `Dataset` — one instance of a schema, scoped via GenericFK to a data owner (in Watch: currently Action or Category). The schema/dataset separation exists because multiple owners often share the same table shape (e.g., every action in a plan has the same budgeting columns).
- `DataPoint` — one cell: `(dataset, date, metric, dimension_categories) → Decimal` value.
- `Dimension` / `DimensionCategory` — the dataset system has its own dimension models, separate from the legacy indicator dimensions.

Supporting models: `DataPointComment`, `DataSource`, `DatasetSourceReference`.

## Target Architecture: Indicator Datasets

### Connecting Indicators to Datasets

Each indicator can optionally own a Dataset, replacing IndicatorValues for that indicator. The connection:

```
Indicator ──[1:1]──► DatasetSchema
                         │
                         ├── DatasetMetric (units_replaced, emission_factor, total_emissions, ...)
                         ├── DatasetMetric (cost_per_unit, total_cost, ...)
                         └── DatasetSchemaDimension (optional: by district, by type, ...)
                              └── Dimension
                                   └── DimensionCategory

Indicator ──[1:1]──► Dataset
                         ├── DataPoint (date, metric, dimension_categories → value)
                         └── IndicatorGoalDataPoint (date, metric, dimension_categories → value)
```

The Indicator gets a `OneToOneField` to `DatasetSchema`. Since each indicator has its own schema, the schema and dataset are effectively 1:1 with the indicator. This is different from the Action/Category use case where many objects share one schema — but the same model machinery works for both.

If we later notice that indicator schemas follow recurring patterns, we can add a template/common-schema mechanism (analogous to how `CommonIndicator` relates to `Indicator`).

### Goals

Goals (target values) share the same tabular shape as actuals — same metrics, same dimensions — but are semantically distinct: "where we want to be" vs. "where we are."

Rather than encoding this distinction as a dimension category or using separate Dataset instances, the `DataPoint` model is refactored into an abstract base with two concrete implementations:

```python
# In kausal_common/datasets/models.py
class DataPointBase(UserModifiableModel, UUIDIdentifiedModel, PermissionedModel):
    """Abstract base for tabular data cells."""
    dataset = ForeignKey(Dataset, related_name='+')
    dimension_categories = ManyToManyField(DimensionCategory)
    date = DateField()
    metric = ForeignKey(DatasetMetric)
    value = DecimalField(max_digits=32, decimal_places=16, null=True)

    class Meta:
        abstract = True

class DataPoint(DataPointBase):
    """Actual/measured values."""
    # Keeps existing related_name='data_points' on dataset FK
    # Retains relationships: comments, source_references
    pass

# In indicators/ (Watch-only)
class IndicatorGoalDataPoint(DataPointBase):
    """Target/goal values for an indicator's dataset."""
    # Points to the same Dataset as the indicator's DataPoints.
    # No comments or source references — goals are infrequently set
    # and don't need the same audit trail.
    pass
```

Both tables reference the same `Dataset` instance (and thus the same schema). The distinction between actuals and goals is structural — which table the row lives in — rather than encoded in the data. This means:

- **Goals can use a subset of metrics.** A refrigerant indicator might only set goals for `total_emissions`, not for `units_replaced` or `emission_factor`. Metrics without goal rows are simply absent.
- **Computed metrics work identically** on both actuals and goals. If a goal is set for `units_replaced` and `emission_factor`, the computation pipeline produces a virtual `total_emissions` goal.
- **No extra dimensions or identifiers** are needed to tell actuals from goals.
- **Comments and source references** remain on `DataPoint` only, since goals are set infrequently and don't need per-cell audit trails.

### Scoping

`DatasetSchema` and `Dataset` use GenericFK-based scoping. For indicator datasets:

- **DatasetSchema** scope → the `Indicator` instance
- **Dataset** scope → the `Indicator` instance

This extends the existing Watch scope types:

```python
# Current
type DatasetScopeType = Action | Category
type DatasetSchemaScopeType = Plan | CategoryType

# Extended
type DatasetScopeType = Action | Category | Indicator
type DatasetSchemaScopeType = Plan | CategoryType | Indicator
```

### Computed Metrics

Some metrics in a schema are derived from others via simple arithmetic. Rather than a DSL or expression language, computations are modeled as explicit operations — a lightweight pipeline of binary operations.

`DatasetMetricComputation` lives in `kausal_common/datasets/models.py`:

```python
class DatasetMetricComputation(OrderedModel):
    schema = ParentalKey(DatasetSchema, related_name='computations')
    target_metric = OneToOneField(DatasetMetric, related_name='computed_by')
    operation = CharField(choices=['multiply', 'divide', 'add', 'subtract'])
    operand_a = ForeignKey(DatasetMetric, null=True, blank=True)  # NULL = virtual
    operand_b = ForeignKey(DatasetMetric)
```

If chained computations are needed (e.g., `A × B = C`, then `C + D = E`), the ordering field provides a natural topological sort — earlier computations produce intermediate metrics that later ones can reference.

#### Virtual metrics (NULL operand_a)

When `operand_a` is `NULL`, the computation uses the indicator's own legacy `IndicatorValue` rows as input. This is a transitional bridge: indicators still store their primary time series as `IndicatorValue` floats, and factors (emission factors, cost factors, etc.) are stored as `DataPoint` rows in the dataset system. The computation multiplies them together.

For example, a refrigerant replacement indicator might have:
- **Metric 0 (virtual)**: "Units replaced" — the indicator's own `IndicatorValue` data. No `DatasetMetric` or `DataPoint` rows exist for this; values are resolved at read time.
- **Metric 1 (factor)**: "Emission factor (tCO2e/unit)" — a `DatasetMetric` with `DataPoint` rows entered by the user.
- **Result metric**: "Total emissions (tCO2e)" — a computed `DatasetMetric` whose values are never stored.

The computation: `NULL × emission_factor = total_emissions`, i.e., `indicator_values × factor = result`.

When all indicators eventually migrate to the dataset system, the NULL operand pattern can be retired and `operand_a` would point to a real `DatasetMetric`.

#### Resolver pattern (`dataset_config`)

The computation service in `kausal_common/datasets/computation.py` is project-agnostic — it doesn't import Watch-specific models. When it encounters a NULL `operand_a`, it delegates to a project-configured resolver:

```
kausal_common/datasets/computation.py
  └── _inject_null_operand_values()
        └── dataset_config.resolve_null_operand_values(dataset)
              │
              └── aplans/dataset_config.py  (Watch implementation)
                    └── Fetches IndicatorValue rows for the dataset's scoped indicator
                        and returns dict[(date, frozenset[dim_cat_ids])] → Decimal
```

The resolver is configured via `kausal_common/datasets/config.py`, which imports the `dataset_config` module from the consuming project (Watch or Paths) by name.

#### Virtual datapoints in the dataset editor

The dataset editor UI displays all data in a unified table — including the virtual metric's values that come from `IndicatorValue` rows rather than `DataPoint` rows. Hooks in `aplans/dataset_config.py` synthesize a virtual metric definition and synthetic datapoint dicts from the indicator's values, shaped identically to real metrics and datapoints so the editor can render them in the same table. The synthetic entries use deterministic UUIDs (`uuid5`) so their identities are stable across requests. Virtual datapoints are read-only in the editor.

##### Date convention mismatch

The two data systems use different date conventions for yearly data: `IndicatorValue` dates use December 31 (`YYYY-12-31`), while the dataset editor stores `DataPoint` dates as January 1 (`YYYY-01-01`). The resolver normalizes `IndicatorValue` dates to match the `DataPoint` convention before injecting them into the computation lookup — without this, dates wouldn't align and no computations would produce results.

#### Compute on read, not on write

Given the small data volumes per indicator (typically tens to low hundreds of data points), computed values are **not persisted** as DataPoints. Instead:

1. Only user-entered (non-computed) metrics are stored as DataPoints.
2. When data is read via GraphQL or REST, the computation service applies the pipeline and produces `ComputedValue` dataclass instances for computed metrics.
3. For NULL operand computations, indicator values are fetched and injected into the values lookup before computation.

This avoids stale-data bugs and keeps the source of truth unambiguous: if a DataPoint exists in the database, a human entered it.

#### Computation service flow

```
compute_dataset_values(dataset)
  │
  ├── 1. Fetch DatasetMetricComputation rows for the dataset's schema
  ├── 2. _build_values_lookup(data_points) → dict[(date, dims, metric_id)] → value
  ├── 3. _inject_null_operand_values(values, dataset, computations)
  │       └── If any comp has operand_a=NULL: call resolver, inject with metric_id=None
  ├── 4. _compute_metric_values(values, computations)
  │       └── For each computation, find matching (date, dims) pairs and apply the operation
  └── 5. _resolve_computed_values(raw) → list[ComputedValue]
          └── Bulk-fetch DatasetMetric and DimensionCategory ORM instances
```

The lookup dict uses `metric_id=None` as the sentinel key for virtual indicator values. This naturally integrates with real metric IDs — the computation engine doesn't need special cases beyond the key convention.

#### Unit derivation

When a factor is added in the admin UI, the result metric's unit is pre-filled using pint: `indicator.unit × factor.unit`. For example, `appliance × tCO2e/appliance → tCO2e`. If pint can't simplify (unknown units), the unit is concatenated as a string (e.g., `"widget * EUR/widget"`). The field is always editable.

### Migration Strategy

Both systems coexist. The approach:

1. Existing indicators continue using `IndicatorValue` unchanged.
2. New multi-metric indicators use the Dataset system.
3. The presence of a `dataset_schema` on an Indicator signals which mode it uses.
4. GraphQL exposes both:
   - `values` — legacy IndicatorValues (existing field, unchanged)
   - `dataset` — new Dataset with DataPoints including computed metrics
5. The UI queries both fields and renders whichever is populated.
6. Eventually, all indicators migrate to datasets, and the legacy system is retired. At that point, the legacy `indicators.Dimension` models get replaced by `kausal_common.datasets.Dimension` equivalents.

### Dimensions

The two dimension systems remain separate:

- **Legacy indicators** use `indicators.Dimension` / `indicators.DimensionCategory`
- **Indicator datasets** use `kausal_common.datasets.Dimension` / `kausal_common.datasets.DimensionCategory`

No attempt is made to unify them now. When the eventual full migration happens, legacy dimensions will be converted to dataset dimensions.

## Model Summary

### Existing models (unchanged)

| Model | Location | Role |
|-------|----------|------|
| `Indicator` | `indicators/models/indicator.py` | Core indicator entity |
| `IndicatorValue` | `indicators/models/values.py` | Legacy single-float time series |
| `IndicatorGoal` | `indicators/models/values.py` | Legacy target values |
| `indicators.Dimension` | `indicators/models/dimensions.py` | Legacy classification axes |
| `DatasetSchema` | `kausal_common/datasets/models.py` | Table shape definition |
| `DatasetMetric` | `kausal_common/datasets/models.py` | Column in a schema |
| `Dataset` | `kausal_common/datasets/models.py` | Table instance |

### Modified models

| Model | Location | Change |
|-------|----------|--------|
| `DataPoint` | `kausal_common/datasets/models.py` | Refactored: core fields extracted into abstract `DataPointBase`; `DataPoint` inherits from it and retains `comments` and `source_references` relationships |

### New models / fields

| Change | Location | Role |
|--------|----------|------|
| `DataPointBase` | `kausal_common/datasets/models.py` | Abstract base: dataset FK, date, metric, value, dimension_categories |
| `Indicator.dataset_schema` | `indicators/models/indicator.py` | OneToOneField linking indicator to its dataset schema |
| `IndicatorGoalDataPoint` | `indicators/models/` (new) | Concrete `DataPointBase` subclass for goal/target values; no comments or source references |
| `DatasetMetricComputation` | `indicators/models/` (new) | Defines a computed metric as a binary operation on two other metrics |
| Scope type extensions | `kausal_common/datasets/models.py` | Add `Indicator` to `DatasetScopeType` and `DatasetSchemaScopeType` |
