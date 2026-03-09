from __future__ import annotations

import pytest

from aplans.cache import PlanSpecificCache

from actions.tests.factories import ActionFactory, CategoryFactory, CategoryTypeFactory, PlanFactory
from datasets.tests.factories import DatasetFactory, DatasetSchemaFactory, DatasetSchemaScopeFactory
from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory

pytestmark = pytest.mark.django_db


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
        """Indicator dataset with plan-scoped schema and IndicatorLevel is indexed under 'indicators.Indicator'."""
        indicator = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=plan)
        ds = DatasetFactory.create(schema=schema, scope=indicator)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert 'indicators.Indicator' in result
        assert indicator.id in result['indicators.Indicator']
        assert result['indicators.Indicator'][indicator.id][str(schema.uuid)] == ds

    def test_indicator_dataset_not_returned_when_not_linked_to_plan(self, plan):
        """Indicator dataset is not returned when the indicator has no IndicatorLevel for the plan."""
        indicator = IndicatorFactory.create()
        # No IndicatorLevel linking this indicator to the plan
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=plan)
        DatasetFactory.create(schema=schema, scope=indicator)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert 'indicators.Indicator' not in result

    def test_indicator_dataset_excluded_from_action_datasets(self, plan):
        """
        Indicator-scoped dataset whose schema is plan-scoped does not appear under 'actions.Action'.

        This holds even though the action_datasets query is otherwise plan-scoped.
        """
        indicator = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=plan)
        DatasetFactory.create(schema=schema, scope=indicator)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert 'actions.Action' not in result

    def test_datasets_for_multiple_model_types_in_single_result(self, plan):
        """Action, category and indicator datasets are all present in a single result dict."""
        action = ActionFactory.create(plan=plan)
        category_type = CategoryTypeFactory.create(plan=plan)
        category = CategoryFactory.create(type=category_type)
        indicator = IndicatorFactory.create()
        IndicatorLevelFactory.create(indicator=indicator, plan=plan)

        action_schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=action_schema, scope=plan)
        action_ds = DatasetFactory.create(schema=action_schema, scope=action)

        category_schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=category_schema, scope=category_type)
        category_ds = DatasetFactory.create(schema=category_schema, scope=category)

        indicator_schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=indicator_schema, scope=plan)
        indicator_ds = DatasetFactory.create(schema=indicator_schema, scope=indicator)

        cache = PlanSpecificCache(plan)
        result = cache.datasets_by_scope_by_schema

        assert result['actions.Action'][action.id][str(action_schema.uuid)] == action_ds
        assert result['actions.Category'][category.id][str(category_schema.uuid)] == category_ds
        assert result['indicators.Indicator'][indicator.id][str(indicator_schema.uuid)] == indicator_ds
