from datetime import date
from factory import SubFactory, Sequence, LazyFunction, LazyAttribute
from actions.tests.factories import ActionFactory, PlanFactory
from aplans.factories import ModelFactory
from budget.models import Dimension, DimensionCategory, DataPoint, Dataset, DatasetSchema, DatasetSchemaScope
from django.contrib.contenttypes.models import ContentType

import uuid

class DimensionFactory(ModelFactory[Dimension]):
    uuid = LazyFunction(uuid.uuid4)
    name = Sequence(lambda i: f"Dimension {i}")

    class Meta:
        model = Dimension

class DimensionCategoryFactory(ModelFactory[DimensionCategory]):
    uuid = LazyFunction(uuid.uuid4)
    dimension = SubFactory(DimensionFactory)
    label = Sequence(lambda i: f"Category {i}")

    class Meta:
        model = DimensionCategory


class DatasetSchemaFactory(ModelFactory[DatasetSchema]):
    uuid = LazyFunction(uuid.uuid4)
    time_resolution = DatasetSchema.TimeResolution.YEARLY
    unit = Sequence(lambda i: f"Unit {i}")
    name = Sequence(lambda i: f"Dataset schema {i}")

    class Meta:
        model = DatasetSchema


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


class DataPointFactory(ModelFactory[DataPoint]):
    uuid = LazyFunction(uuid.uuid4)
    dataset = SubFactory(DatasetFactory)
    date = Sequence(lambda i: date(2023, 1, i+1))
    value = Sequence(lambda i: float(i))

    class Meta:
        model = DataPoint
