from datetime import date
from factory import SubFactory, Sequence, LazyFunction, LazyAttribute
from actions.tests.factories import ActionFactory
from aplans.factories import ModelFactory
from budget.models import Dimension, DimensionCategory, Dataset, DataPoint, DatasetScope
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

class DatasetFactory(ModelFactory[Dataset]):
    uuid = LazyFunction(uuid.uuid4)
    time_resolution = Dataset.TimeResolution.YEARLY
    unit = Sequence(lambda i: f"Unit {i}")

    class Meta:
        model = Dataset

class DataPointFactory(ModelFactory[DataPoint]):
    uuid = LazyFunction(uuid.uuid4)
    dataset = SubFactory(DatasetFactory)
    date = Sequence(lambda i: date(2023, 1, i+1))
    value = Sequence(lambda i: float(i))

    class Meta:
        model = DataPoint

class DatasetScopeFactory(ModelFactory[DatasetScope]):
    dataset = SubFactory(DatasetFactory)
    scope_content_type = LazyAttribute(lambda obj: ContentType.objects.get_for_model(obj.scope))
    scope_id = LazyAttribute(lambda obj: obj.scope.id)
    scope = SubFactory(ActionFactory)

    class Meta:
        model = DatasetScope
