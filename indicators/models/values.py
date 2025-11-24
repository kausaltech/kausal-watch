from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, ClassVar, cast

import reversion
from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel

if TYPE_CHECKING:
    from kausal_common.models.types import FK

    from indicators.models import Indicator


class IndicatorGraph(models.Model):
    indicator: FK[Indicator] = models.ForeignKey('indicators.Indicator', related_name='graphs', on_delete=models.CASCADE)
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    public_fields: ClassVar = ['id', 'indicator', 'data', 'created_at']

    class Meta:
        get_latest_by = 'created_at'

    def __str__(self):
        return "%s (%s)" % (self.indicator, self.created_at)


class IndicatorValue(ClusterableModel):
    """One measurement of an indicator for a certain date/month/year."""

    indicator = ParentalKey['Indicator'](
        'indicators.Indicator', related_name='values', on_delete=models.CASCADE,
        verbose_name=_('indicator'),
    )
    categories = models.ManyToManyField(
        'indicators.DimensionCategory', related_name='values', blank=True, verbose_name=_('categories'),
    )
    value = models.FloatField(verbose_name=_('value'))
    date = models.DateField(verbose_name=_('date'))

    # Cached here for performance reasons
    normalized_values: models.JSONField[dict[str, float]] = models.JSONField(null=True, blank=True)

    public_fields: ClassVar = ['id', 'indicator', 'categories', 'value', 'date']

    class Meta:
        verbose_name = _('indicator value')
        verbose_name_plural = _('indicator values')
        ordering = ('indicator', 'date')
        get_latest_by = 'date'

    def clean(self):
        super().clean()
        # FIXME: Check for duplicates on categories

    def format_date(self) -> str:
        indicator = cast('Indicator', self.indicator)  # pyright: ignore[reportUnnecessaryCast]
        resolution = indicator.time_resolution
        if isinstance(self.date, datetime.date):
            if resolution == 'year':
                return self.date.strftime('%Y')
            if resolution == 'month':
                return self.date.strftime('%Y-%m')
            return self.date.isoformat()
        return self.date

    def __str__(self):
        indicator = self.indicator
        if isinstance(self.date, datetime.date):
            date_str = self.date.isoformat()
        else:
            date_str = self.date

        return f"{indicator} {date_str} {self.value}"


@reversion.register()
class IndicatorGoal(models.Model):
    """The numeric goal which the organization has set for an indicator."""

    indicator = ParentalKey['Indicator'](
        'indicators.Indicator', related_name='goals', on_delete=models.CASCADE,
        verbose_name=_('indicator'),
    )
    value = models.FloatField()
    date = models.DateField(verbose_name=_('date'))

    # Cached here for performance reasons
    normalized_values: models.JSONField[dict[str, float] | None] = models.JSONField(null=True, blank=True)

    public_fields: ClassVar = ['id', 'indicator', 'value', 'date']

    class Meta:
        verbose_name = _('indicator goal')
        verbose_name_plural = _('indicator goals')
        ordering = ('indicator', 'date')
        get_latest_by = 'date'
        unique_together = (('indicator', 'date'),)

    def __str__(self):
        indicator = self.indicator
        date = self.date.isoformat()

        return f"{indicator} {date} {self.value}"
