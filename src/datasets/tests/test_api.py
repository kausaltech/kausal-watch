"""
Tests for the dataset REST API.

Focuses on the DataPoint duplicate-detection logic
and the computed_data_points endpoint.

Key behaviours verified:
  - Yearly datasets: duplicate = same calendar year (unchanged)
  - Monthly datasets: duplicate = same calendar year **and** month (new)
  - Monthly datasets: two points in different months of the same year are allowed
    (previously blocked by a ValueError that has been removed)
  - computed_data_points: no result when only one operand has a data point (bug fix)
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from rest_framework import serializers as drf_serializers

import pytest

from kausal_common.datasets.api import DataPointSerializer
from kausal_common.datasets.models import DatasetMetricComputation, DatasetSchema

from datasets.tests.factories import (
    DataPointFactory,
    DatasetFactory,
    DatasetMetricFactory,
    DatasetSchemaDimensionFactory,
    DatasetSchemaFactory,
    DimensionCategoryFactory,
    DimensionFactory,
)

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_serializer(dataset_uuid: str) -> DataPointSerializer:
    """Return a DataPointSerializer whose view-context points at *dataset_uuid*."""
    mock_view = MagicMock()
    mock_view.kwargs = {'dataset_uuid': dataset_uuid}
    return DataPointSerializer(context={'view': mock_view})


def _make_monthly_dataset():
    """Create a minimal monthly dataset with one metric and one dimension category."""
    schema = DatasetSchemaFactory.create(
        time_resolution=DatasetSchema.TimeResolution.MONTHLY,
    )
    metric = DatasetMetricFactory.create(schema=schema)
    dimension = DimensionFactory.create()
    category = DimensionCategoryFactory.create(dimension=dimension)
    DatasetSchemaDimensionFactory.create(schema=schema, dimension=dimension)
    dataset = DatasetFactory.create(schema=schema)
    return dataset, metric, category


def _make_yearly_dataset():
    """Create a minimal yearly dataset with one metric and one dimension category."""
    schema = DatasetSchemaFactory.create(
        time_resolution=DatasetSchema.TimeResolution.YEARLY,
    )
    metric = DatasetMetricFactory.create(schema=schema)
    dimension = DimensionFactory.create()
    category = DimensionCategoryFactory.create(dimension=dimension)
    DatasetSchemaDimensionFactory.create(schema=schema, dimension=dimension)
    dataset = DatasetFactory.create(schema=schema)
    return dataset, metric, category


# ---------------------------------------------------------------------------
# Yearly duplicate detection (unchanged behaviour)
# ---------------------------------------------------------------------------


class TestYearlyDuplicateDetection:
    """
    For yearly datasets, a duplicate is defined by (year, metric, categories).

    Different months within the same year are still considered duplicates.
    """

    def test_same_year_same_categories_rejected(self):
        """Two points with the same year and dimension categories must fail."""
        dataset, metric, category = _make_yearly_dataset()
        dp = DataPointFactory.create(
            dataset=dataset,
            metric=metric,
            date=date(2024, 1, 1),
            value=1.0,
        )
        dp.dimension_categories.set([category])

        serializer = _make_serializer(str(dataset.uuid))

        with pytest.raises(drf_serializers.ValidationError):
            serializer.validate({
                'date': date(2024, 6, 15),  # same year, different month
                'dimension_categories': [category],
                'metric': metric,
            })

    def test_different_years_allowed(self):
        """Two points in different years with the same categories are valid."""
        dataset, metric, category = _make_yearly_dataset()
        dp = DataPointFactory.create(
            dataset=dataset,
            metric=metric,
            date=date(2023, 1, 1),
            value=1.0,
        )
        dp.dimension_categories.set([category])

        serializer = _make_serializer(str(dataset.uuid))

        # Should not raise
        result = serializer.validate({
            'date': date(2024, 1, 1),
            'dimension_categories': [category],
            'metric': metric,
        })
        assert result['date'] == date(2024, 1, 1)

    def test_same_year_different_categories_allowed(self):
        """Same year and metric but different dimension categories must pass."""
        dataset, metric, category = _make_yearly_dataset()
        other_category = DimensionCategoryFactory.create(
            dimension=category.dimension,
        )
        dp = DataPointFactory.create(
            dataset=dataset,
            metric=metric,
            date=date(2024, 1, 1),
            value=1.0,
        )
        dp.dimension_categories.set([category])

        serializer = _make_serializer(str(dataset.uuid))

        result = serializer.validate({
            'date': date(2024, 3, 1),
            'dimension_categories': [other_category],
            'metric': metric,
        })
        assert result['date'] == date(2024, 3, 1)


# ---------------------------------------------------------------------------
# Monthly duplicate detection (new behaviour)
# ---------------------------------------------------------------------------


class TestMonthlyDuplicateDetection:
    """
    For monthly datasets, a duplicate is defined by (year, month, metric, categories).

    Two points in different months of the same year must be allowed.
    """

    def test_same_month_same_categories_rejected(self):
        """Two points in the same year-month with the same categories must fail."""
        dataset, metric, category = _make_monthly_dataset()
        dp = DataPointFactory.create(
            dataset=dataset,
            metric=metric,
            date=date(2024, 3, 1),
            value=5.0,
        )
        dp.dimension_categories.set([category])

        serializer = _make_serializer(str(dataset.uuid))

        with pytest.raises(drf_serializers.ValidationError):
            serializer.validate({
                'date': date(2024, 3, 15),  # same year+month
                'dimension_categories': [category],
                'metric': metric,
            })

    def test_different_months_same_year_allowed(self):
        """
        Two points in different months of the same year must be valid.

        This is the key regression guard: before the fix, this would have raised
        a ValueError ('Only yearly time resolution supported currently.').
        """
        dataset, metric, category = _make_monthly_dataset()
        dp = DataPointFactory.create(
            dataset=dataset,
            metric=metric,
            date=date(2024, 1, 1),
            value=1.0,
        )
        dp.dimension_categories.set([category])

        serializer = _make_serializer(str(dataset.uuid))

        # Must not raise -- different month in the same year
        result = serializer.validate({
            'date': date(2024, 3, 1),
            'dimension_categories': [category],
            'metric': metric,
        })
        assert result['date'] == date(2024, 3, 1)

    def test_same_month_different_categories_allowed(self):
        """Same month and metric but different dimension categories must pass."""
        dataset, metric, category = _make_monthly_dataset()
        other_category = DimensionCategoryFactory.create(
            dimension=category.dimension,
        )
        dp = DataPointFactory.create(
            dataset=dataset,
            metric=metric,
            date=date(2024, 3, 1),
            value=5.0,
        )
        dp.dimension_categories.set([category])

        serializer = _make_serializer(str(dataset.uuid))

        result = serializer.validate({
            'date': date(2024, 3, 1),
            'dimension_categories': [other_category],
            'metric': metric,
        })
        assert result['date'] == date(2024, 3, 1)

    def test_different_years_allowed(self):
        """Same month number but in different years must be valid."""
        dataset, metric, category = _make_monthly_dataset()
        dp = DataPointFactory.create(
            dataset=dataset,
            metric=metric,
            date=date(2023, 3, 1),
            value=5.0,
        )
        dp.dimension_categories.set([category])

        serializer = _make_serializer(str(dataset.uuid))

        result = serializer.validate({
            'date': date(2024, 3, 1),
            'dimension_categories': [category],
            'metric': metric,
        })
        assert result['date'] == date(2024, 3, 1)

    def test_no_existing_points_always_allowed(self):
        """With an empty dataset, any data point must be accepted."""
        dataset, metric, category = _make_monthly_dataset()

        serializer = _make_serializer(str(dataset.uuid))

        result = serializer.validate({
            'date': date(2024, 3, 1),
            'dimension_categories': [category],
            'metric': metric,
        })
        assert result['date'] == date(2024, 3, 1)


# ---------------------------------------------------------------------------
# API integration tests via the REST endpoint
# ---------------------------------------------------------------------------


class TestDataPointAPIMonthly:
    """Integration tests for POST /v1/datasets/{uuid}/data_points/ on monthly datasets."""

    @pytest.fixture
    def monthly_setup(self):
        """Return (dataset, metric, category) for a monthly-resolution dataset."""
        return _make_monthly_dataset()

    def _url(self, dataset_uuid) -> str:
        return f'/v1/datasets/{dataset_uuid}/data_points/'

    def test_create_monthly_data_point_succeeds(self, api_client, superuser, monthly_setup):
        """POSTing a data point to a monthly dataset must return HTTP 201."""
        dataset, metric, category = monthly_setup
        api_client.force_login(superuser)

        response = api_client.post(
            self._url(dataset.uuid),
            data={
                'date': '2024-03-01',
                'value': 42.0,
                'metric': str(metric.uuid),
                'dimension_categories': [str(category.uuid)],
            },
        )
        assert response.status_code == 201, response.json_data

    def test_monthly_duplicate_in_same_month_rejected(self, api_client, superuser, monthly_setup):
        """POSTing a second data point with the same year-month, metric and categories must return HTTP 400."""
        dataset, metric, category = monthly_setup
        api_client.force_login(superuser)
        url = self._url(dataset.uuid)
        payload = {
            'date': '2024-03-01',
            'value': 10.0,
            'metric': str(metric.uuid),
            'dimension_categories': [str(category.uuid)],
        }

        first = api_client.post(url, data=payload)
        assert first.status_code == 201, first.json_data

        second = api_client.post(url, data=payload)
        assert second.status_code == 400

    def test_monthly_different_months_same_year_both_succeed(self, api_client, superuser, monthly_setup):
        """
        Two data points in different months of the same year must both be created successfully.

        This is the core new capability enabled by the backend fix.
        """
        dataset, metric, category = monthly_setup
        api_client.force_login(superuser)
        url = self._url(dataset.uuid)

        jan = api_client.post(
            url,
            data={
                'date': '2024-01-01',
                'value': 1.0,
                'metric': str(metric.uuid),
                'dimension_categories': [str(category.uuid)],
            },
        )
        assert jan.status_code == 201, jan.json_data

        mar = api_client.post(
            url,
            data={
                'date': '2024-03-01',
                'value': 3.0,
                'metric': str(metric.uuid),
                'dimension_categories': [str(category.uuid)],
            },
        )
        assert mar.status_code == 201, mar.json_data

    def test_monthly_same_month_different_categories_both_succeed(self, api_client, superuser, monthly_setup):
        """Different dimension categories in the same month must both be accepted."""
        dataset, metric, category = monthly_setup
        other_category = DimensionCategoryFactory.create(
            dimension=category.dimension,
        )
        # Also attach the new category to the schema's dimension
        DatasetSchemaDimensionFactory.create(
            schema=dataset.schema,
            dimension=other_category.dimension,
        )
        api_client.force_login(superuser)
        url = self._url(dataset.uuid)

        r1 = api_client.post(
            url,
            data={
                'date': '2024-03-01',
                'value': 1.0,
                'metric': str(metric.uuid),
                'dimension_categories': [str(category.uuid)],
            },
        )
        assert r1.status_code == 201, r1.json_data

        r2 = api_client.post(
            url,
            data={
                'date': '2024-03-01',
                'value': 2.0,
                'metric': str(metric.uuid),
                'dimension_categories': [str(other_category.uuid)],
            },
        )
        assert r2.status_code == 201, r2.json_data


# ---------------------------------------------------------------------------
# computed_data_points endpoint
# ---------------------------------------------------------------------------


def _make_computation_setup():
    """
    Create a schema with three metrics where c = a * b.

    Return (dataset, metric_a, metric_b, metric_c).
    """
    schema = DatasetSchemaFactory.create()
    metric_a = DatasetMetricFactory.create(schema=schema)
    metric_b = DatasetMetricFactory.create(schema=schema)
    metric_c = DatasetMetricFactory.create(schema=schema)
    DatasetMetricComputation.objects.create(
        schema=schema,
        operation='multiply',
        operand_a=metric_a,
        operand_b=metric_b,
        target_metric=metric_c,
    )
    dataset = DatasetFactory.create(schema=schema)
    return dataset, metric_a, metric_b, metric_c


class TestComputedDataPoints:
    """Tests for GET /v1/datasets/{uuid}/computed_data_points/."""

    def _url(self, dataset_uuid) -> str:
        return f'/v1/datasets/{dataset_uuid}/computed_data_points/'

    def test_no_result_when_only_one_operand_has_data(self, api_client, superuser):
        """
        Return no result when only one operand has a data point.

        This guards against the bug where _compute_metric_values() emitted a
        null ComputedValue whenever any one operand was present, even if the
        other operand had no data point at all.
        """
        dataset, metric_a, _metric_b, _metric_c = _make_computation_setup()
        DataPointFactory.create(dataset=dataset, metric=metric_a, date=date(2024, 1, 1), value=Decimal(3))

        api_client.force_login(superuser)
        response = api_client.get(self._url(dataset.uuid))

        assert response.status_code == 200
        assert response.json_data == []

    def test_computed_value_returned_when_both_operands_present(self, api_client, superuser):
        """When both operands have data points the computed result must be returned."""
        dataset, metric_a, metric_b, metric_c = _make_computation_setup()
        DataPointFactory.create(dataset=dataset, metric=metric_a, date=date(2024, 1, 1), value=Decimal(3))
        DataPointFactory.create(dataset=dataset, metric=metric_b, date=date(2024, 1, 1), value=Decimal(5))

        api_client.force_login(superuser)
        response = api_client.get(self._url(dataset.uuid))

        assert response.status_code == 200
        assert len(response.json_data) == 1
        result = response.json_data[0]
        assert result['date'] == '2024-01-01'
        assert Decimal(result['value']) == Decimal(15)
        assert result['metric'] == str(metric_c.uuid)

    def test_no_result_when_dataset_has_no_data_points(self, api_client, superuser):
        """An empty dataset must return an empty list."""
        dataset, _metric_a, _metric_b, _metric_c = _make_computation_setup()

        api_client.force_login(superuser)
        response = api_client.get(self._url(dataset.uuid))

        assert response.status_code == 200
        assert response.json_data == []

    def test_partial_dates_produce_no_null_results(self, api_client, superuser):
        """
        Return results only for dates covered by both operands.

        Operand a has data for two dates, while operand b covers only one.
        """
        dataset, metric_a, metric_b, _metric_c = _make_computation_setup()
        DataPointFactory.create(dataset=dataset, metric=metric_a, date=date(2023, 1, 1), value=Decimal(2))
        DataPointFactory.create(dataset=dataset, metric=metric_a, date=date(2024, 1, 1), value=Decimal(4))
        DataPointFactory.create(dataset=dataset, metric=metric_b, date=date(2024, 1, 1), value=Decimal(5))

        api_client.force_login(superuser)
        response = api_client.get(self._url(dataset.uuid))

        assert response.status_code == 200
        assert len(response.json_data) == 1
        result = response.json_data[0]
        assert result['date'] == '2024-01-01'
        assert Decimal(result['value']) == Decimal(20)
