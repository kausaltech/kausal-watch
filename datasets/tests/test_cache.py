from __future__ import annotations

import pytest

from aplans.cache import PlanSpecificCache

from actions.tests.factories import ActionFactory, CategoryFactory, CategoryTypeFactory, PlanFactory
from datasets.tests.factories import DatasetFactory, DatasetSchemaFactory, DatasetSchemaScopeFactory
from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory

pytestmark = pytest.mark.django_db


class TestGetDatasetSchemasForObjectOutOfPlan:
    """Tests that get_dataset_schemas_for_object returns [] for objects outside the active plan."""

    def test_action_from_other_plan_returns_empty(self, plan):
        """Action belonging to a different plan returns empty list instead of crashing."""
        other_plan = PlanFactory.create()
        action = ActionFactory.create(plan=other_plan)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=plan)

        cache = PlanSpecificCache(plan)
        assert cache.get_dataset_schemas_for_object(action) == []

    def test_indicator_not_in_plan_returns_empty(self, plan):
        """Indicator with no IndicatorLevel for the plan returns empty list instead of crashing."""
        indicator = IndicatorFactory.create()
        # No IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=plan)

        cache = PlanSpecificCache(plan)
        assert cache.get_dataset_schemas_for_object(indicator) == []


class TestGetDatasetSchemasForObjectInPlan:
    """Tests that get_dataset_schemas_for_object pairs schemas with their datasets for in-plan objects."""

    def test_action_in_plan_no_dataset_returns_schema_none(self, plan):
        """Action in plan with no dataset returns [(schema, None)] for each schema."""
        action = ActionFactory.create(plan=plan)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=plan)

        cache = PlanSpecificCache(plan)
        results = cache.get_dataset_schemas_for_object(action)

        assert len(results) == 1
        result_schema, result_dataset = results[0]
        assert result_schema == schema
        assert result_dataset is None

    def test_action_in_plan_with_dataset_returns_schema_dataset(self, plan):
        """Action in plan with a matching dataset returns [(schema, dataset)]."""
        action = ActionFactory.create(plan=plan)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=plan)
        ds = DatasetFactory.create(schema=schema, scope=action)

        cache = PlanSpecificCache(plan)
        results = cache.get_dataset_schemas_for_object(action)

        assert len(results) == 1
        result_schema, result_dataset = results[0]
        assert result_schema == schema
        assert result_dataset == ds

    def test_action_in_plan_multiple_schemas_paired_correctly(self, plan):
        """Action in plan with two schemas: one has a dataset, the other does not."""
        action = ActionFactory.create(plan=plan)
        schema_with_ds = DatasetSchemaFactory.create()
        schema_without_ds = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema_with_ds, scope=plan)
        DatasetSchemaScopeFactory.create(schema=schema_without_ds, scope=plan)
        ds = DatasetFactory.create(schema=schema_with_ds, scope=action)

        cache = PlanSpecificCache(plan)
        results = cache.get_dataset_schemas_for_object(action)

        assert len(results) == 2
        result_map = dict(results)
        assert result_map[schema_with_ds] == ds
        assert result_map[schema_without_ds] is None

    def test_indicator_in_plan_no_dataset_returns_schema_none(self, plan):
        """Indicator linked to plan via IndicatorLevel with own schema but no dataset returns [(schema, None)]."""
        schema = DatasetSchemaFactory.create()
        indicator = IndicatorFactory.create(dataset_schema=schema)
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)

        cache = PlanSpecificCache(plan)
        results = cache.get_dataset_schemas_for_object(indicator)

        assert len(results) == 1
        result_schema, result_dataset = results[0]
        assert result_schema == schema
        assert result_dataset is None

    def test_indicator_in_plan_with_dataset_returns_schema_dataset(self, plan):
        """Indicator linked to plan with own schema and a matching dataset returns [(schema, dataset)]."""
        schema = DatasetSchemaFactory.create()
        indicator = IndicatorFactory.create(dataset_schema=schema)
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        DatasetSchemaScopeFactory.create(schema=schema, scope=indicator)
        ds = DatasetFactory.create(schema=schema, scope=indicator)

        cache = PlanSpecificCache(plan)
        results = cache.get_dataset_schemas_for_object(indicator)

        assert len(results) == 1
        result_schema, result_dataset = results[0]
        assert result_schema == schema
        assert result_dataset == ds

    def test_category_with_dataset_returns_schema_dataset(self, plan):
        """Category with an existing dataset returns [(schema, dataset)] not [(schema, None)]."""
        category_type = CategoryTypeFactory.create(plan=plan)
        category = CategoryFactory.create(type=category_type)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=category_type)
        ds = DatasetFactory.create(schema=schema, scope=category)

        cache = PlanSpecificCache(plan)
        results = cache.get_dataset_schemas_for_object(category)

        assert len(results) == 1
        result_schema, result_dataset = results[0]
        assert result_schema == schema
        assert result_dataset == ds


class TestPlanIndicatorIds:
    """Tests for PlanSpecificCache.plan_indicator_ids."""

    def test_empty_when_no_indicators_in_plan(self, plan):
        """Returns empty frozenset when no indicators are linked to the plan."""
        cache = PlanSpecificCache(plan)
        assert cache.plan_indicator_ids == frozenset()

    def test_returns_ids_of_plan_indicators(self, plan):
        """Returns frozenset containing the IDs of all indicators linked to the plan."""
        indicator1 = IndicatorFactory.create()
        indicator2 = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator1, plan=plan)
        IndicatorLevelFactory.create(indicator=indicator2, plan=plan)

        cache = PlanSpecificCache(plan)
        assert cache.plan_indicator_ids == frozenset({indicator1.id, indicator2.id})

    def test_does_not_include_indicators_from_other_plans(self, plan):
        """Indicators linked only to other plans are not included."""
        from actions.tests.factories import PlanFactory

        other_plan = PlanFactory.create()
        indicator_in_plan = IndicatorFactory.create()
        indicator_other_plan = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator_in_plan, plan=plan)
        IndicatorLevelFactory.create(indicator=indicator_other_plan, plan=other_plan)

        cache = PlanSpecificCache(plan)
        assert indicator_in_plan.id in cache.plan_indicator_ids
        assert indicator_other_plan.id not in cache.plan_indicator_ids


class TestCategoryTypeDatasetSchemaLookup:
    """Tests for looking up DatasetSchemas scoped to CategoryTypes via PlanSpecificCache."""

    def test_get_dataset_schemas_for_category_with_category_type_scope(self, plan):
        """Test that schemas scoped to a CategoryType are returned for categories of that type."""
        category_type = CategoryTypeFactory.create(plan=plan)
        category = CategoryFactory.create(type=category_type)

        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=category_type)

        cache = PlanSpecificCache(plan)
        results = cache.get_dataset_schemas_for_object(category)

        assert len(results) == 1
        result_schema, result_dataset = results[0]
        assert result_schema == schema
        assert result_dataset is None

    def test_get_dataset_schemas_for_category_returns_empty_for_other_category_type(self, plan):
        """Test that schemas scoped to a different CategoryType are not returned."""
        category_type1 = CategoryTypeFactory.create(plan=plan)
        category_type2 = CategoryTypeFactory.create(plan=plan)
        category1 = CategoryFactory.create(type=category_type1)
        category2 = CategoryFactory.create(type=category_type2)

        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=category_type1)

        cache = PlanSpecificCache(plan)

        results_for_cat1 = cache.get_dataset_schemas_for_object(category1)
        assert len(results_for_cat1) == 1
        assert results_for_cat1[0][0] == schema

        results_for_cat2 = cache.get_dataset_schemas_for_object(category2)
        assert len(results_for_cat2) == 0

    def test_get_dataset_schemas_for_category_multiple_schemas_same_type(self, plan):
        """Test that multiple schemas scoped to the same CategoryType are all returned."""
        category_type = CategoryTypeFactory.create(plan=plan)
        category = CategoryFactory.create(type=category_type)

        schema1 = DatasetSchemaFactory.create()
        schema2 = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema1, scope=category_type)
        DatasetSchemaScopeFactory.create(schema=schema2, scope=category_type)

        cache = PlanSpecificCache(plan)
        results = cache.get_dataset_schemas_for_object(category)

        assert len(results) == 2
        assert {s for s, _ in results} == {schema1, schema2}


class TestDatasetsByScopeBySchemaCached:
    """Tests for PlanSpecificCache.datasets_by_scope_by_schema."""

    def test_empty_when_no_datasets(self, plan):
        """Returns empty dict when no datasets exist for the plan."""
        cache = PlanSpecificCache(plan)
        assert cache.datasets_by_scope_by_schema == {}

    def test_action_dataset_indexed_by_action_id_and_schema_uuid(self, plan):
        """Action dataset with plan-scoped schema is indexed under 'actions.Action'."""
        action = ActionFactory.create(plan=plan)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=plan)
        ds = DatasetFactory.create(schema=schema, scope=action)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert 'actions.Action' in result
        assert action.id in result['actions.Action']
        assert str(schema.uuid) in result['actions.Action'][action.id]
        assert result['actions.Action'][action.id][str(schema.uuid)] == ds

    def test_action_dataset_not_returned_for_different_plan(self, plan):
        """Action dataset whose schema is scoped to a different plan is not returned."""
        other_plan = PlanFactory.create()
        action = ActionFactory.create(plan=plan)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=other_plan)
        DatasetFactory.create(schema=schema, scope=action)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert 'actions.Action' not in result

    def test_multiple_schemas_for_same_action(self, plan):
        """Multiple schemas for the same action are each indexed by their UUID."""
        action = ActionFactory.create(plan=plan)
        schema1 = DatasetSchemaFactory.create()
        schema2 = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema1, scope=plan)
        DatasetSchemaScopeFactory.create(schema=schema2, scope=plan)
        ds1 = DatasetFactory.create(schema=schema1, scope=action)
        ds2 = DatasetFactory.create(schema=schema2, scope=action)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert result['actions.Action'][action.id][str(schema1.uuid)] == ds1
        assert result['actions.Action'][action.id][str(schema2.uuid)] == ds2

    def test_category_dataset_indexed_under_actions_category(self, plan):
        """Category dataset with category-type-scoped schema is indexed under 'actions.Category'."""
        category_type = CategoryTypeFactory.create(plan=plan)
        category = CategoryFactory.create(type=category_type)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=category_type)
        ds = DatasetFactory.create(schema=schema, scope=category)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert 'actions.Category' in result
        assert category.id in result['actions.Category']
        assert result['actions.Category'][category.id][str(schema.uuid)] == ds

    def test_non_category_dataset_with_category_type_schema_scope_not_indexed_as_category(self, plan):
        """
        Non-category dataset with a CategoryType schema scope is not indexed as category.

        A dataset scoped to an Action whose schema is scoped to a CategoryType
        must not appear under 'actions.Category'.
        """
        category_type = CategoryTypeFactory.create(plan=plan)
        action = ActionFactory.create(plan=plan)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=category_type)
        DatasetFactory.create(schema=schema, scope=action)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert 'actions.Category' not in result

    def test_category_dataset_not_returned_for_other_plans_category_type(self, plan):
        """Category dataset scoped to a CategoryType from a different plan is not returned."""
        other_plan = PlanFactory.create()
        other_category_type = CategoryTypeFactory.create(plan=other_plan)
        category = CategoryFactory.create(type=other_category_type)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=other_category_type)
        DatasetFactory.create(schema=schema, scope=category)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert 'actions.Category' not in result

    def test_indicator_dataset_indexed_under_indicators_indicator(self, plan):
        """Indicator dataset with own 1:1 schema and IndicatorLevel is indexed under 'indicators.Indicator'."""
        schema = DatasetSchemaFactory.create()
        indicator = IndicatorFactory.create(dataset_schema=schema)
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        DatasetSchemaScopeFactory.create(schema=schema, scope=indicator)
        ds = DatasetFactory.create(schema=schema, scope=indicator)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert 'indicators.Indicator' in result
        assert indicator.id in result['indicators.Indicator']
        assert result['indicators.Indicator'][indicator.id][str(schema.uuid)] == ds

    def test_indicator_dataset_not_returned_when_not_linked_to_plan(self, plan):
        """Indicator dataset is not returned when the indicator has no IndicatorLevel for the plan."""
        schema = DatasetSchemaFactory.create()
        indicator = IndicatorFactory.create(dataset_schema=schema)
        DatasetSchemaScopeFactory.create(schema=schema, scope=indicator)
        # No IndicatorLevel linking this indicator to the plan
        DatasetFactory.create(schema=schema, scope=indicator)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert 'indicators.Indicator' not in result

    def test_indicator_dataset_excluded_from_action_datasets(self, plan):
        """Indicator-scoped dataset does not appear under 'actions.Action'."""
        schema = DatasetSchemaFactory.create()
        indicator = IndicatorFactory.create(dataset_schema=schema)
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        DatasetSchemaScopeFactory.create(schema=schema, scope=indicator)
        DatasetFactory.create(schema=schema, scope=indicator)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert 'actions.Action' not in result

    def test_datasets_for_multiple_model_types_in_single_result(self, plan):
        """Action, category and indicator datasets are all present in a single result dict."""
        action = ActionFactory.create(plan=plan)
        category_type = CategoryTypeFactory.create(plan=plan)
        category = CategoryFactory.create(type=category_type)
        indicator_schema = DatasetSchemaFactory.create()
        indicator = IndicatorFactory.create(dataset_schema=indicator_schema)
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        DatasetSchemaScopeFactory.create(schema=indicator_schema, scope=indicator)

        action_schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=action_schema, scope=plan)
        action_ds = DatasetFactory.create(schema=action_schema, scope=action)

        category_schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=category_schema, scope=category_type)
        category_ds = DatasetFactory.create(schema=category_schema, scope=category)

        indicator_ds = DatasetFactory.create(schema=indicator_schema, scope=indicator)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert result['actions.Action'][action.id][str(action_schema.uuid)] == action_ds
        assert result['actions.Category'][category.id][str(category_schema.uuid)] == category_ds
        assert result['indicators.Indicator'][indicator.id][str(indicator_schema.uuid)] == indicator_ds
