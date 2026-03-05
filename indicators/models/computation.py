from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey

from aplans.utils import OrderedModel

if TYPE_CHECKING:
    from modelcluster.fields import PK

    from kausal_common.datasets.models import DatasetMetric, DatasetSchema
    from kausal_common.models.types import FK


class DatasetMetricComputation(OrderedModel):
    """
    Define a computed metric as a binary operation on two other metrics.

    Computed metrics are never stored as DataPoints — they are calculated
    on read. The ordering field provides a natural topological sort for
    chained computations: earlier computations produce intermediate metrics
    that later ones can reference.
    """

    class Operation(models.TextChoices):
        MULTIPLY = 'multiply', _('Multiply')
        DIVIDE = 'divide', _('Divide')
        ADD = 'add', _('Add')
        SUBTRACT = 'subtract', _('Subtract')

    schema: PK[DatasetSchema] = ParentalKey(
        'datasets.DatasetSchema',
        on_delete=models.CASCADE,
        related_name='computations',
        verbose_name=_('schema'),
    )
    target_metric: FK[DatasetMetric] = models.ForeignKey(
        'datasets.DatasetMetric',
        on_delete=models.CASCADE,
        related_name='computed_by',
        verbose_name=_('target metric'),
        help_text=_('The metric whose values are computed by this operation'),
    )
    operation = models.CharField(
        max_length=16,
        choices=Operation.choices,
        verbose_name=_('operation'),
    )
    operand_a: FK[DatasetMetric] = models.ForeignKey(
        'datasets.DatasetMetric',
        on_delete=models.CASCADE,
        related_name='+',
        verbose_name=_('operand A'),
    )
    operand_b: FK[DatasetMetric] = models.ForeignKey(
        'datasets.DatasetMetric',
        on_delete=models.CASCADE,
        related_name='+',
        verbose_name=_('operand B'),
    )

    objects: ClassVar[models.Manager[Self]] = models.Manager()

    class Meta:
        verbose_name = _('dataset metric computation')
        verbose_name_plural = _('dataset metric computations')
        ordering = ['schema', 'order']

    def __str__(self):
        return f'{self.target_metric} = {self.operand_a} {self.operation} {self.operand_b}'

    def filter_siblings(self, qs: models.QuerySet[Self]) -> models.QuerySet[Self]:
        return qs.filter(schema=self.schema)
