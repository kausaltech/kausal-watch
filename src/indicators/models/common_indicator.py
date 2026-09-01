from __future__ import annotations

import typing
from typing import TYPE_CHECKING, ClassVar, Self

import reversion
from django.db import models
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from wagtail.fields import RichTextField

from aplans.utils import IdentifierField

from indicators.models.relationships import IndicatorRelationship

if TYPE_CHECKING:
    from kausal_common.models.types import M2M, RevMany

    from actions.models.plan import Plan
    from indicators.models.indicator import Indicator


@reversion.register()
class CommonIndicator(ClusterableModel):
    identifier = IdentifierField[str | None](null=True, blank=True, max_length=70)
    name = models.CharField(max_length=200, verbose_name=_('name'))
    description = RichTextField[str | None, str | None](null=True, blank=True, verbose_name=_('description'))

    quantity = ParentalKey(
        'indicators.Quantity',
        related_name='common_indicators',
        on_delete=models.PROTECT,
        verbose_name=pgettext_lazy('physical', 'quantity'),
    )
    unit = ParentalKey(
        'indicators.Unit',
        related_name='common_indicators',
        on_delete=models.PROTECT,
        verbose_name=_('unit'),
    )
    plans: M2M[Plan, PlanCommonIndicator] = models.ManyToManyField(
        'actions.Plan',
        blank=True,
        related_name='common_indicators',
        through='PlanCommonIndicator',
    )
    normalization_indicators: M2M[Self, CommonIndicatorNormalizator] = models.ManyToManyField(
        'self',
        blank=True,
        related_name='normalizable_indicators',
        symmetrical=False,
        through='CommonIndicatorNormalizator',
        through_fields=('normalizable', 'normalizer'),
    )
    normalize_by_label = models.CharField(
        max_length=200,
        verbose_name=_('normalize by label'),
        null=True,
        blank=True,
    )

    i18n = TranslationField(fields=['name', 'description', 'normalize_by_label'])

    public_fields: ClassVar = [
        'id',
        'identifier',
        'name',
        'description',
        'quantity',
        'unit',
        'indicators',
        'dimensions',
        'related_causes',
        'related_effects',
        'normalization_indicators',
        'normalize_by_label',
        'normalizations',
    ]

    normalizations: RevMany[CommonIndicatorNormalizator]
    indicators: RevMany[Indicator]

    class Meta:
        verbose_name = _('common indicator')
        verbose_name_plural = _('common indicators')

    def __str__(self):
        return self.name

    def autocomplete_label(self):
        return str(self)


class CommonIndicatorNormalizator(models.Model):
    normalizable = models.ForeignKey('indicators.CommonIndicator', on_delete=models.CASCADE, related_name='normalizations')
    normalizer = models.ForeignKey('indicators.CommonIndicator', on_delete=models.CASCADE, related_name='+')
    unit = models.ForeignKey('indicators.Unit', on_delete=models.PROTECT, related_name='+')
    unit_multiplier = models.FloatField()

    class Meta:
        unique_together = (('normalizable', 'normalizer'),)

    def __str__(self) -> str:
        return "'%s' normalized by '%s'" % (self.normalizable, self.normalizer)


class PlanCommonIndicator(models.Model):
    common_indicator = models.ForeignKey('indicators.CommonIndicator', on_delete=models.CASCADE, related_name='+')
    plan = models.ForeignKey('actions.Plan', on_delete=models.CASCADE, related_name='plan_common_indicator_through')

    def __str__(self):
        return '%s in %s' % (self.common_indicator, self.plan)


class RelatedCommonIndicator(IndicatorRelationship):
    causal_indicator = models.ForeignKey(
        'indicators.CommonIndicator',
        related_name='related_effects',
        on_delete=models.CASCADE,
        verbose_name=_('causal indicator'),
    )
    effect_indicator = models.ForeignKey(
        'indicators.CommonIndicator',
        related_name='related_causes',
        on_delete=models.CASCADE,
        verbose_name=_('effect indicator'),
    )

    public_fields: typing.ClassVar = ['id', 'causal_indicator', 'effect_indicator', 'effect_type']

    class Meta:
        unique_together = (('causal_indicator', 'effect_indicator'),)
        verbose_name = _('related indicator')
        verbose_name_plural = _('related indicators')


class FrameworkIndicator(models.Model):
    identifier = IdentifierField[str | None](null=True, blank=True, max_length=70)
    common_indicator = ParentalKey(
        'indicators.CommonIndicator',
        related_name='frameworks',
        on_delete=models.CASCADE,
        verbose_name=_('common indicator'),
    )
    framework = ParentalKey(
        'indicators.Framework',
        related_name='common_indicators',
        on_delete=models.CASCADE,
        verbose_name=_('framework'),
    )

    public_fields: ClassVar = ['id', 'identifier', 'common_indicator', 'framework']

    class Meta:
        verbose_name = _('framework indicator')
        verbose_name_plural = _('framework indicators')

    def __str__(self):
        return '%s ∈ %s' % (str(self.common_indicator), str(self.framework))
