from typing import Any

from rest_framework import serializers, viewsets, permissions
from rest_framework_nested import routers

from aplans.api_router import router
from .models import DataPoint, Dataset, Dimension, DimensionCategory


all_routers = []


class OptionalInputField:
    def validate_empty_values(self, data: Any) -> tuple[bool, Any]:
        if data is serializers.empty:
            # We allow it to be null in incoming data
            raise serializers.SkipField
        return super().validate_empty_values(data)


class OptionalInputCharField(OptionalInputField, serializers.CharField):
    pass


class OptionalInputIntegerField(OptionalInputField, serializers.IntegerField):
    pass


class OptionalInputUUIDField(OptionalInputField, serializers.UUIDField):
    pass


class DimensionCategorySerializer(serializers.ModelSerializer):
    uuid = OptionalInputUUIDField()
    # Reference dimension by UUID instead of PK
    dimension = serializers.SlugRelatedField(slug_field='uuid', read_only=True)
    label = OptionalInputCharField(source='label_i18n')
    order = OptionalInputIntegerField()

    class Meta:
        model = DimensionCategory
        fields = ['uuid', 'dimension', 'label', 'order']


class DatasetSerializer(serializers.ModelSerializer):
    unit = serializers.CharField(source='unit_i18n')

    class Meta:
        model = Dataset
        fields = ['uuid', 'time_resolution', 'unit']


class DatasetViewSet(viewsets.ModelViewSet):
    queryset = Dataset.objects.all()
    lookup_field = 'uuid'
    serializer_class = DatasetSerializer
    permission_classes = (
        permissions.DjangoModelPermissions,
    )


class DataPointSerializer(serializers.ModelSerializer):
    # Reference dataset by UUID instead of PK
    dataset = serializers.SlugRelatedField(slug_field='uuid', read_only=True)
    dimension_categories = DimensionCategorySerializer(many=True)

    class Meta:
        model = DataPoint
        fields = ['uuid', 'dataset', 'dimension_categories', 'date', 'value']


class DataPointViewSet(viewsets.ModelViewSet):
    queryset = DataPoint.objects.all()
    lookup_field = 'uuid'
    serializer_class = DataPointSerializer
    permission_classes = (
        permissions.DjangoModelPermissions,
    )


class DimensionSerializer(serializers.ModelSerializer):
    categories = DimensionCategorySerializer(many=True)
    name = serializers.CharField(source='name_i18n')

    class Meta:
        model = Dimension
        fields = ['uuid', 'name', 'categories']


class DimensionViewSet(viewsets.ModelViewSet):
    queryset = Dimension.objects.all()
    lookup_field = 'uuid'
    serializer_class = DimensionSerializer
    permission_classes = (
        permissions.DjangoModelPermissions,
    )


router.register(r'datasets', DatasetViewSet, basename='dataset')
dataset_router = routers.NestedSimpleRouter(router, r'datasets', lookup='dataset')
all_routers.append(dataset_router)
dataset_router.register(r'datapoints', DataPointViewSet, basename='datapoint')
router.register(r'dimensions', DimensionViewSet, basename='dimension')
dimension_router = routers.NestedSimpleRouter(router, r'dimensions', lookup='dimension')
all_routers.append(dimension_router)
