from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, Self, override

import reversion
from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel

from wagtail_color_panel.fields import ColorField

from aplans.utils import OrderedModel

if TYPE_CHECKING:
    from modelcluster.fields import PK

    from kausal_common.models.types import RevMany

    from actions.models.plan import Plan
    from indicators.models.indicator import Indicator
    from indicators.models.values import IndicatorValue


@reversion.register()
class Dimension(ClusterableModel):
    """
    A dimension for indicators.

    Dimensions will have several dimension categories.
    """

    name = models.CharField(max_length=100, verbose_name=_('name'))

    public_fields: ClassVar = ['id', 'name', 'categories']

    # type annotations
    categories: RevMany[DimensionCategory]
    plans: RevMany[PlanDimension]

    class Meta:
        verbose_name = _('dimension')
        verbose_name_plural = _('dimensions')

    def __str__(self):
        return self.name

    @override
    def delete(
        self, using: Any | None = None, keep_parents: bool = False, **kwargs: dict[str, Any]
    ) -> tuple[int, dict[str, int]]:
        # Check if dimension is used by multiple plans
        if self.plans.count() > 1:
            from django.core.exceptions import ValidationError

            plan_names = [str(pd.plan) for pd in self.plans.all()]
            raise ValidationError(
                _('Cannot delete dimension "%(dimension)s" because it is linked to multiple plans: %(plans)s')
                % {'dimension': self.name, 'plans': ', '.join(plan_names)}
            )
        return super().delete(using=using, keep_parents=keep_parents, **kwargs)


class DimensionCategory(OrderedModel):
    """
    A category in a dimension.

    Indicator values are grouped with this.
    """

    dimension = ParentalKey('indicators.Dimension', on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100, verbose_name=_('name'))
    default_color = ColorField(
        max_length=50,
        blank=True,
        default='',
        verbose_name=_('default color'),
        help_text=_('Default color for this dimension category in charts'),
    )

    public_fields: ClassVar = ['id', 'dimension', 'name', 'default_color', 'order']

    # type annotations
    values: RevMany[IndicatorValue]

    def filter_siblings(self, qs: models.QuerySet[Self]) -> models.QuerySet[Self]:
        return qs.filter(dimension=self.dimension)

    class Meta:
        verbose_name = _('dimension category')
        verbose_name_plural = _('dimension categories')
        ordering = ['dimension', 'order']

    def __str__(self):
        return self.name


class PlanDimension(models.Model):
    """Mapping of which dimensions a plan is using."""

    dimension = ParentalKey('indicators.Dimension', on_delete=models.CASCADE, related_name='plans')
    plan: ParentalKey[Plan] = ParentalKey('actions.Plan', on_delete=models.CASCADE, related_name='dimensions')

    class Meta:
        verbose_name = _('plan dimension')
        verbose_name_plural = _('plan dimensions')
        unique_together = (('plan', 'dimension'),)

    def __str__(self):
        return '%s ∈ %s' % (str(self.dimension), str(self.plan))


class IndicatorDimension(OrderedModel):
    """Mapping of which dimensions an indicator has."""

    dimension: PK[Dimension] = ParentalKey('indicators.Dimension', on_delete=models.CASCADE, related_name='instances')
    indicator: PK[Indicator] = ParentalKey('indicators.Indicator', on_delete=models.CASCADE, related_name='dimensions')

    public_fields: ClassVar = ['id', 'dimension', 'indicator', 'order']

    def filter_siblings(self, qs: models.QuerySet[Self]) -> models.QuerySet[Self]:
        return qs.filter(indicator=self.indicator)

    class Meta:
        verbose_name = _('indicator dimension')
        verbose_name_plural = _('indicator dimensions')
        ordering = ['indicator', 'order']
        indexes = [
            models.Index(fields=['indicator', 'order']),
        ]
        unique_together = (('indicator', 'dimension'),)

    def __str__(self):
        return '%s ∈ %s' % (str(self.dimension), str(self.indicator))


class CommonIndicatorDimension(OrderedModel):
    """Mapping of which dimensions a common indicator has."""

    dimension = ParentalKey('indicators.Dimension', on_delete=models.CASCADE, related_name='common_indicators')
    common_indicator = ParentalKey('indicators.CommonIndicator', on_delete=models.CASCADE, related_name='dimensions')

    public_fields: ClassVar = ['id', 'dimension', 'common_indicator', 'order']

    def filter_siblings(self, qs: models.QuerySet[Self]) -> models.QuerySet[Self]:
        return qs.filter(common_indicator=self.common_indicator)

    class Meta:
        verbose_name = _('common indicator dimension')
        verbose_name_plural = _('common indicator dimensions')
        ordering = ['common_indicator', 'order']
        indexes = [
            models.Index(fields=['common_indicator', 'order']),
        ]
        unique_together = (('common_indicator', 'dimension'),)

    def __str__(self):
        return '%s ∈ %s' % (str(self.dimension), str(self.common_indicator))
