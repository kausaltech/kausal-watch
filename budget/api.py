from modeltrans.conf import get_available_languages
from modeltrans.translator import get_i18n_field
from modeltrans.utils import build_localized_fieldname
from rest_framework import permissions, serializers, viewsets
from rest_framework.fields import Field

from rest_framework_nested import routers

from aplans.api_router import router

from .models import DataPoint, Dataset, DatasetSchema, DatasetSchemaDimensionCategory, Dimension, DimensionCategory

all_routers = []


class I18nFieldSerializerMixin:
    Meta: object
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        i18n_field = get_i18n_field(self.Meta.model)  # type: ignore[attr-defined]
        if i18n_field:
            for source_field in i18n_field.fields:
                if source_field not in self.Meta.fields:  # type: ignore[attr-defined]
                    continue
                # When reading, serialize the field using `<x>_i18n` to display the value in currently active language.
                current_language_field = build_localized_fieldname(source_field, 'i18n')
                self.fields[source_field] = serializers.CharField(  # type: ignore[attr-defined]
                    source=current_language_field, read_only=True,
                )
                # Require language to be explicit when writing to a translatable field. That is, when writing, we expect
                # that `<x>_en` is present, for example; `<x>` should not work.
                for lang in get_available_languages():
                    translated_field = build_localized_fieldname(source_field, lang)
                    self.fields[translated_field] = serializers.CharField(  # type: ignore[attr-defined]
                        write_only=True, required=False,
                    )


class DimensionCategorySerializer(I18nFieldSerializerMixin, serializers.ModelSerializer[DimensionCategory]):
    dimension = serializers.SlugRelatedField(slug_field='uuid', read_only=True)  # type: ignore[var-annotated]
    label = serializers.CharField(source='label_i18n')  # type: ignore[assignment]

    class Meta:
        model = DimensionCategory
        fields = ['uuid', 'label', 'dimension']


class DatasetSchemaDimensionCategorySerializer(serializers.ModelSerializer):
    category = DimensionCategorySerializer(many=False, required=False)

    class Meta:
        model = DatasetSchemaDimensionCategory
        fields = ['order', 'category']


class DataPointSerializer(serializers.ModelSerializer):
    dataset: Field = serializers.SlugRelatedField(slug_field='uuid', read_only=True)
    dimension_categories = serializers.SlugRelatedField(
        # FIXME: Restrict queryset to dimension categories available to the dataset
        slug_field='uuid', many=True, queryset=DimensionCategory.objects.all(),
    )
    value = serializers.DecimalField(max_digits=10, decimal_places=4, coerce_to_string=False, allow_null=True)

    class Meta:
        model = DataPoint
        fields = ['uuid', 'dataset', 'dimension_categories', 'date', 'value']

    def create(self, validated_data):
        dimension_categories = validated_data.pop('dimension_categories')
        data_point = super().create(validated_data)
        dataset = data_point.dataset
        assert dataset == validated_data['dataset']
        allowed_dimension_categories = [dc.category for dc in dataset.schema.dimension_categories.all()]
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
    dimension_categories = DatasetSchemaDimensionCategorySerializer(
        many=True, required=False,
    )

    class Meta:
        model = DatasetSchema
        fields = ['uuid', 'time_resolution', 'unit', 'name', 'dimension_categories', 'start_date']


class DatasetSchemaViewSet(viewsets.ModelViewSet):
    queryset = DatasetSchema.objects.all()
    lookup_field = 'uuid'
    serializer_class = DatasetSchemaSerializer
    permission_classes = (
        permissions.DjangoModelPermissions,
    )


class DatasetSerializer(I18nFieldSerializerMixin, serializers.ModelSerializer):
    data_points: Field = serializers.SlugRelatedField(slug_field='uuid', read_only=True, many=True)
    schema = serializers.SlugRelatedField(slug_field='uuid', queryset=DatasetSchema.objects.all())

    class Meta:
        model = Dataset
        fields = ['uuid', 'schema', 'data_points', 'scope_id', 'scope_content_type']


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
