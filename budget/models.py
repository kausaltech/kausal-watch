from __future__ import annotations

import uuid
from functools import lru_cache

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField

from aplans.utils import OrderedModel

from actions.models.action import Action
from actions.models.category import Category, CategoryType
from actions.models.plan import Plan


class Dimension(ClusterableModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=100, verbose_name=_('name'))

    i18n = TranslationField(fields=['name'])
    name_i18n: str

    class Meta:
        verbose_name = _('dimension')
        verbose_name_plural = _('dimensions')
        ordering = ('name',)

    def __str__(self):
        return self.name_i18n


class DimensionCategory(OrderedModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    dimension = ParentalKey(Dimension, blank=False, on_delete=models.CASCADE, related_name='categories')
    label = models.CharField(max_length=100, verbose_name=_('label'))

    i18n = TranslationField(fields=['label'])
    label_i18n: str

    class Meta:
        verbose_name = _('dimension category')
        verbose_name_plural = _('dimension categories')

    def __str__(self):
        if self.label:
            return f'{self.label_i18n} ({self.uuid})'
        return str(self.uuid)


class DimensionScope(OrderedModel):
    """Link a dimension to a context in which it can be used, such as a plan or a category type."""

    dimension = models.ForeignKey(Dimension, on_delete=models.CASCADE, related_name='scopes')
    scope_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    scope_id = models.PositiveIntegerField()
    scope: models.ForeignKey[Plan, Plan] | models.ForeignKey[CategoryType, CategoryType] = GenericForeignKey(  # pyright: ignore
        'scope_content_type', 'scope_id',
    ) # type: ignore[assignment]


class DatasetSchema(models.Model):
    class TimeResolution(models.TextChoices):
        """
        Time resolution of all data points.

        If a dataset has, e.g., monthly time resolution, then each data point applies to the entire month in which
        the data point's time is.
        """

        # TBD: Could also be separate model. (Some customers might be very creative in their granularities.)
        YEARLY = 'yearly', _('Yearly')
        # QUARTERLY = 'quarterly', _('Quarterly')
        # MONTHLY = 'monthly', _('Monthly')
        # WEEKLY = 'weekly', _('Weekly')
        # DAILY = 'daily', _('Daily')
        # HOURLY = 'hourly', _('Hourly')

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    time_resolution = models.CharField(
        max_length=16, choices=TimeResolution.choices,
        default=TimeResolution.YEARLY,
        help_text=_('Time resolution of the time stamps of data points in this dataset'),
    )
    unit = models.CharField(max_length=100, blank=True, verbose_name=_('unit'))
    name = models.CharField(max_length=100, blank=False, verbose_name=_('name'))
    start_date = models.DateField(
        verbose_name=_('start date'),
        blank=True,
        null=True,
        help_text=_("First applicable date for datapoints in these datasets"),
    )

    i18n = TranslationField(fields=['unit', 'name'])
    unit_i18n: str
    name_i18n: str

    def __str__(self):
        if self.name_i18n:
            return f'{self.name_i18n} ({self.uuid})'
        return str(self.uuid)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        DatasetSchema.get_for_scope.cache_clear()

    @staticmethod
    @lru_cache
    def get_for_scope(scope_id: int, scope_content_type_id: int) -> list[DatasetSchema]:
        return list(
            DatasetSchema.objects.filter(
                scopes__scope_id=scope_id, scopes__scope_content_type__id=scope_content_type_id,
            ),
        )

    @staticmethod
    def get_for_model(obj: models.Model) -> list[DatasetSchema]:
        scope_id = None
        scope_content_type_id = None
        if isinstance(obj, Action):
            scope_id = obj.plan.pk
            scope_content_type_id = ContentType.objects.get_for_model(Plan).pk
        elif isinstance(obj, Category):
            scope_id = obj.type.pk
            scope_content_type_id = ContentType.objects.get_for_model(CategoryType).pk
        if scope_id is not None:
            return DatasetSchema.get_for_scope(scope_id, scope_content_type_id)
        return []

    def delete(self, *args, **kwargs):
        retval = super().delete(*args, **kwargs)
        DatasetSchema.get_for_scope.cache_clear()
        return retval


class DatasetSchemaDimensionCategory(OrderedModel):
    schema = models.ForeignKey(
        DatasetSchema,
        on_delete=models.PROTECT,
        related_name='dimension_categories',
        null=False,
        blank=False,
    )
    category = models.ForeignKey(DimensionCategory, related_name='schemas', on_delete=models.PROTECT, null=False, blank=False)

    def filter_siblings(
        self,
        qs: models.QuerySet[DatasetSchemaDimensionCategory],
    ) -> models.QuerySet[DatasetSchemaDimensionCategory]:
        return qs.filter(schema=self.schema, category__dimension=self.category.dimension)


class Dataset(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    schema = models.ForeignKey(
        DatasetSchema, null=True, blank=True, related_name='datasets',
        verbose_name=_('schema'), on_delete=models.PROTECT,
    )
    # The "scope" generic foreign key links this dataset to an action or category
    scope_content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, related_name='+',
        null=True, blank=True,
    )
    scope_id = models.PositiveIntegerField(null=True, blank=True)
    scope: models.ForeignKey[Action, Action] | models.ForeignKey[Category, Category] = GenericForeignKey(  # pyright: ignore
        'scope_content_type', 'scope_id',
    ) # type: ignore[assignment]

    class Meta:  # pyright:ignore
        verbose_name = _('dataset')
        verbose_name_plural = _('datasets')
        ordering = ('id',)
        constraints = (
            models.UniqueConstraint(
                fields=['schema', 'scope_content_type', 'scope_id'],
                name='unique_dataset_per_instance_per_schema',
            ),
        )

    def __str__(self):
        return f'Dataset {self.uuid}'

    def save(self, *args, **kwargs):
        if self.schema is None:
            self.schema = DatasetSchema.objects.create()
        super().save(*args, **kwargs)


class DatasetSchemaScope(models.Model):
    """Link a dataset schema to a context in which it can be used, such as a plan."""

    schema = models.ForeignKey(DatasetSchema, on_delete=models.CASCADE, related_name='scopes')
    scope_content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name='+')
    scope_id = models.PositiveIntegerField()
    # If scope is a Plan, this schema can be used for Actions in that plan
    scope: models.ForeignKey[Plan, Plan] | models.ForeignKey[CategoryType, CategoryType] = GenericForeignKey(  # pyright: ignore
        'scope_content_type', 'scope_id',
    ) # type: ignore[assignment]

    def __str__(self):
        return f'DatasetSchemaScope schema:{self.schema.uuid} scope:{self.scope}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        DatasetSchema.get_for_scope.cache_clear()

    def delete(self, *args, **kwargs):
        retval = super().delete(*args, **kwargs)
        DatasetSchema.get_for_scope.cache_clear()
        return retval


class DataPoint(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    dataset = models.ForeignKey(
        Dataset, related_name='data_points', on_delete=models.CASCADE, verbose_name=_('dataset'),
    )
    dimension_categories = models.ManyToManyField(
        DimensionCategory, related_name='data_points', blank=True, verbose_name=_('dimension categories'),
    )
    date = models.DateField(
        verbose_name=_('date'),
        help_text=_("Date of this data point in context of the dataset's time resolution"),
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        verbose_name=_('value'),
        # null means that the data point is explicitly marked as not available or not applicable, for example
        # - category combination not applicable or
        # - data is known to be unavailable for date
        null=True,
        blank=True,
    )

    class Meta:  # pyright:ignore
        verbose_name = _('data point')
        verbose_name_plural = _('data points')
        ordering = ('date',)
        # TODO: Enforce uniqueness constraint.
        # This doesn't work because dimension_categories is a many-to-many field.
        # constraints = [
        #     models.UniqueConstraint(fields=['dataset', 'dimension_categories', 'date'],
        #                             name='unique_data_point_value')
        # ]

    def __str__(self):
        return f'Datapoint {self.uuid} / dataset {self.dataset.uuid}'
