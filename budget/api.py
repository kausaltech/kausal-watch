from django.conf import settings
from modeltrans.conf import get_available_languages
from modeltrans.translator import get_i18n_field
from modeltrans.utils import build_localized_fieldname
from rest_framework import serializers, viewsets, permissions
from rest_framework_nested import routers
from typing import Any

from aplans.api_router import router
from .models import DataPoint, Dataset, DatasetSchema, Dimension, DimensionCategory


all_routers = []


class I18nFieldSerializerMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        i18n_field = get_i18n_field(self.Meta.model)
        if i18n_field:
            for source_field in i18n_field.fields:
                if source_field not in self.Meta.fields:
                    continue
                # When reading, serialize the field using `<x>_i18n` to display the value in currently active language.
                current_language_field = build_localized_fieldname(source_field, 'i18n')
                self.fields[source_field] = serializers.CharField(source=current_language_field, read_only=True)
                # Require language to be explicit when writing to a translatable field. That is, when writing, we expect
                # that `<x>_en` is present, for example; `<x>` should not work.
                for lang in get_available_languages():
                    translated_field = build_localized_fieldname(source_field, lang)
                    self.fields[translated_field] = serializers.CharField(write_only=True, required=False)


class DimensionCategorySerializer(I18nFieldSerializerMixin, serializers.ModelSerializer):
    # Reference dimension by UUID instead of PK
    # dimension = serializers.SlugRelatedField(slug_field='uuid', read_only=True)  # implicit as router is nested
    label = serializers.CharField(source='label_i18n')

    class Meta:
        model = DimensionCategory
        fields = ['uuid', 'label']


class DataPointSerializer(serializers.ModelSerializer):
    # Reference dataset by UUID instead of PK
    dataset = serializers.SlugRelatedField(slug_field='uuid', read_only=True)
    dimension_categories = serializers.SlugRelatedField(
        # FIXME: Restrict queryset to dimension categories available to the dataset
        slug_field='uuid', many=True, queryset=DimensionCategory.objects.all(),
    )

    class Meta:
        model = DataPoint
        fields = ['uuid', 'dataset', 'dimension_categories', 'date', 'value']

    def create(self, validated_data):
        dimension_categories = validated_data.pop('dimension_categories')
        data_point = super().create(validated_data)
        dataset = data_point.dataset
        assert dataset == validated_data['dataset']
        allowed_dimension_categories = list(dataset.schema.dimension_categories.all())
        for dimension_category in dimension_categories:
            # TODO: Do proper validation instead
            assert dimension_category in allowed_dimension_categories
            data_point.dimension_categories.add(dimension_category)
        return data_point


class DataPointViewSet(viewsets.ModelViewSet):
    lookup_field = 'uuid'
    serializer_class = DataPointSerializer
    permission_classes = (
        permissions.DjangoModelPermissions,
    )

    def get_queryset(self):
        return DataPoint.objects.filter(dataset__uuid=self.kwargs['dataset_uuid'])

    def perform_create(self, serializer):
        dataset_uuid = self.kwargs['dataset_uuid']
        dataset = Dataset.objects.get(uuid=dataset_uuid)
        serializer.save(dataset=dataset)


class DatasetSchemaSerializer(I18nFieldSerializerMixin, serializers.ModelSerializer):
    dimension_categories = serializers.SlugRelatedField(
        slug_field='uuid', many=True, queryset=DimensionCategory.objects.all()
    )

    class Meta:
        model = DatasetSchema
        fields = ['uuid', 'time_resolution', 'unit', 'name', 'dimension_categories']


class DatasetSchemaViewSet(viewsets.ModelViewSet):
    queryset = DatasetSchema.objects.all()
    lookup_field = 'uuid'
    serializer_class = DatasetSchemaSerializer
    permission_classes = (
        permissions.DjangoModelPermissions,
    )


class DatasetSerializer(I18nFieldSerializerMixin, serializers.ModelSerializer):
    data_points = serializers.SlugRelatedField(slug_field='uuid', read_only=True, many=True)
    schema = serializers.SlugRelatedField(slug_field='uuid', queryset=DatasetSchema.objects.all())

    class Meta:
        model = Dataset
        fields = ['uuid', 'schema', 'data_points']


class DatasetViewSet(viewsets.ModelViewSet):
    queryset = Dataset.objects.all()
    lookup_field = 'uuid'
    serializer_class = DatasetSerializer
    permission_classes = (
        permissions.DjangoModelPermissions,
    )


class DimensionSerializer(I18nFieldSerializerMixin, serializers.ModelSerializer):
    categories = DimensionCategorySerializer(many=True, required=False)
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


class DimensionCategoryViewSet(viewsets.ModelViewSet):
    lookup_field = 'uuid'
    serializer_class = DimensionCategorySerializer
    permission_classes = (
        permissions.DjangoModelPermissions,
    )

    def get_queryset(self):
        return DimensionCategory.objects.filter(dimension__uuid=self.kwargs['dimension_uuid'])

    def perform_create(self, serializer):
        dimension_uuid = self.kwargs['dimension_uuid']
        dimension = Dimension.objects.get(uuid=dimension_uuid)
        serializer.save(dimension=dimension)


router.register(r'dataset_schemas', DatasetSchemaViewSet, basename='datasetschema')
router.register(r'datasets', DatasetViewSet, basename='dataset')
dataset_router = routers.NestedSimpleRouter(router, r'datasets', lookup='dataset')
all_routers.append(dataset_router)
dataset_router.register(r'data_points', DataPointViewSet, basename='datapoint')
router.register(r'dimensions', DimensionViewSet, basename='dimension')
dimension_router = routers.NestedSimpleRouter(router, r'dimensions', lookup='dimension')
all_routers.append(dimension_router)
dimension_router.register(r'categories', DimensionCategoryViewSet, basename='category')
