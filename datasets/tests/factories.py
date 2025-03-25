import uuid
from datetime import date

from django.contrib.contenttypes.models import ContentType

from factory import LazyAttribute, LazyFunction, Sequence, SubFactory

from kausal_common.datasets.models import (
    DataPoint,
    Dataset,
    DatasetMetric,
    DatasetSchema,
    DatasetSchemaDimension,
    DatasetSchemaScope,
    Dimension,
    DimensionCategory,
    DimensionScope,
)

from aplans.factories import ModelFactory

from actions.tests.factories import ActionFactory, PlanFactory


class DimensionFactory(ModelFactory[Dimension]):
    uuid = LazyFunction(uuid.uuid4)
    name = Sequence(lambda i: f"Dimension {i}")

    class Meta:
        model = Dimension

class DimensionCategoryFactory(ModelFactory[DimensionCategory]):
    uuid = LazyFunction(uuid.uuid4)
    dimension = SubFactory(DimensionFactory)
    label = Sequence(lambda i: f"Dimension category {i}")

    class Meta:
        model = DimensionCategory


class DimensionScopeFactory(ModelFactory[DimensionScope]):
    dimension = SubFactory(DimensionFactory)
    scope_content_type = LazyAttribute(lambda obj: ContentType.objects.get_for_model(obj.scope))
    scope_id = LazyAttribute(lambda obj: obj.scope.id)
    scope = SubFactory(PlanFactory)

    class Meta:
        model = DimensionScope


class DatasetSchemaFactory(ModelFactory[DatasetSchema]):
    uuid = LazyFunction(uuid.uuid4)
    time_resolution = DatasetSchema.TimeResolution.YEARLY
    name = Sequence(lambda i: f"Dataset schema {i}")

    class Meta:
        model = DatasetSchema


class DatasetSchemaDimensionFactory(ModelFactory[DatasetSchemaDimension]):
    dimension = SubFactory(DimensionFactory)
    schema = SubFactory(DatasetSchemaFactory)

    class Meta:
        model = DatasetSchemaDimension


class DatasetFactory(ModelFactory[Dataset]):
    uuid = LazyFunction(uuid.uuid4)
    schema = SubFactory(DatasetSchemaFactory)
    scope_content_type = LazyAttribute(lambda obj: ContentType.objects.get_for_model(obj.scope))
    scope_id = LazyAttribute(lambda obj: obj.scope.id)
    scope = SubFactory(ActionFactory)

    class Meta:
        model = Dataset


class DatasetSchemaScopeFactory(ModelFactory[DatasetSchemaScope]):
    schema = SubFactory(DatasetSchemaFactory)
    scope_content_type = LazyAttribute(lambda obj: ContentType.objects.get_for_model(obj.scope))
    scope_id = LazyAttribute(lambda obj: obj.scope.id)
    scope = SubFactory(PlanFactory)

    class Meta:
        model = DatasetSchemaScope


class DatasetMetricFactory(ModelFactory[DatasetMetric]):
    schema = SubFactory(DatasetSchemaFactory)
    name = Sequence(lambda i: f"Dataset metric {i}")
    unit = Sequence(lambda i: f"Dataset metric unit {i}")

    class Meta:
        model = DatasetMetric


class DataPointFactory(ModelFactory[DataPoint]):
    uuid = LazyFunction(uuid.uuid4)
    dataset = SubFactory(DatasetFactory)
    metric = SubFactory(DatasetMetricFactory)
    date = Sequence(lambda i: date(2023, 1, i+1))
    value = Sequence(lambda i: float(i))

    class Meta:
        model = DataPoint
