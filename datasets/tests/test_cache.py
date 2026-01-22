from __future__ import annotations

import pytest

from aplans.cache import PlanSpecificCache

from actions.tests.factories import CategoryFactory, CategoryTypeFactory
from datasets.tests.factories import DatasetSchemaFactory, DatasetSchemaScopeFactory

pytestmark = pytest.mark.django_db


class TestCategoryTypeDatasetSchemaLookup:
    """Tests for looking up DatasetSchemas scoped to CategoryTypes via PlanSpecificCache."""

    def test_get_dataset_schemas_for_category_with_category_type_scope(self, plan):
        """Test that schemas scoped to a CategoryType are returned for categories of that type."""
        # Create a CategoryType linked to the plan
        category_type = CategoryTypeFactory.create(plan=plan)
        category = CategoryFactory.create(type=category_type)

        # Create a schema scoped to the category's CategoryType
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=category_type)

        cache = PlanSpecificCache(plan)
        schemas = cache.get_dataset_schemas_for_object(category)

        assert len(schemas) == 1
        assert schemas[0] == schema

    def test_get_dataset_schemas_for_category_returns_empty_for_other_category_type(self, plan):
        """Test that schemas scoped to a different CategoryType are not returned."""
        # Create two CategoryTypes in the same plan
        category_type1 = CategoryTypeFactory.create(plan=plan)
        category_type2 = CategoryTypeFactory.create(plan=plan)
        category1 = CategoryFactory.create(type=category_type1)
        category2 = CategoryFactory.create(type=category_type2)

        # Create a schema scoped to category_type1 only
        schema = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema, scope=category_type1)

        cache = PlanSpecificCache(plan)

        # The schema should be found for category1
        schemas_for_cat1 = cache.get_dataset_schemas_for_object(category1)
        assert len(schemas_for_cat1) == 1
        assert schemas_for_cat1[0] == schema

        # But not for category2 (different CategoryType)
        schemas_for_cat2 = cache.get_dataset_schemas_for_object(category2)
        assert len(schemas_for_cat2) == 0

    def test_get_dataset_schemas_for_category_multiple_schemas_same_type(self, plan):
        """Test that multiple schemas scoped to the same CategoryType are all returned."""
        category_type = CategoryTypeFactory.create(plan=plan)
        category = CategoryFactory.create(type=category_type)

        schema1 = DatasetSchemaFactory.create()
        schema2 = DatasetSchemaFactory.create()
        DatasetSchemaScopeFactory.create(schema=schema1, scope=category_type)
        DatasetSchemaScopeFactory.create(schema=schema2, scope=category_type)

        cache = PlanSpecificCache(plan)
        schemas = cache.get_dataset_schemas_for_object(category)

        assert len(schemas) == 2
        assert set(schemas) == {schema1, schema2}
