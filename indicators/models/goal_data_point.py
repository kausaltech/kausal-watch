from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

from django.db import models
from django.utils.translation import gettext_lazy as _

from kausal_common.datasets.models import DataPointBase, Dataset, DatasetMetric, DimensionCategory

if TYPE_CHECKING:
    from kausal_common.models.types import FK, M2M


class IndicatorGoalDataPoint(DataPointBase):
    dataset: FK[Dataset] = models.ForeignKey(
        Dataset, related_name='goal_data_points', on_delete=models.CASCADE, verbose_name=_('dataset'),
    )
    metric: FK[DatasetMetric] = models.ForeignKey(
        DatasetMetric, related_name='+', on_delete=models.PROTECT, verbose_name=_('metric'),
    )
    dimension_categories: M2M[DimensionCategory, IndicatorGoalDimensionCategory] = models.ManyToManyField(
        DimensionCategory,
        through='IndicatorGoalDimensionCategory',
        blank=True,
        verbose_name=_('dimension categories'),
    )

    objects: ClassVar[models.Manager[Self]] = models.Manager()

    class Meta:
        verbose_name = _('indicator goal data point')
        verbose_name_plural = _('indicator goal data points')
        ordering = ('date', 'id')

    def __str__(self):
        return f'IndicatorGoalDataPoint {self.uuid} / dataset {self.dataset.uuid}'


class IndicatorGoalDimensionCategory(models.Model):
    goal_data_point: FK[IndicatorGoalDataPoint] = models.ForeignKey(
        IndicatorGoalDataPoint, on_delete=models.CASCADE, related_name='dimension_category_links',
    )
    dimension_category: FK[DimensionCategory] = models.ForeignKey(
        DimensionCategory, on_delete=models.PROTECT, related_name='+',
    )

    class Meta:
        verbose_name = _('indicator goal dimension category')
        verbose_name_plural = _('indicator goal dimension categories')
        unique_together = ('goal_data_point', 'dimension_category')

    def __str__(self):
        return f'{self.goal_data_point_id} / {self.dimension_category_id}'
