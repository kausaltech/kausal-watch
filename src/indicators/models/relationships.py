from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey


class IndicatorRelationship(models.Model):
    """A causal relationship between two indicators."""

    INCREASES = 'increases'
    DECREASES = 'decreases'
    PART_OF = 'part_of'

    EFFECT_TYPES = (
        (INCREASES, _('increases')),
        (DECREASES, _('decreases')),
        (PART_OF, _('is a part of')),
    )
    effect_type = models.CharField(
        max_length=40,
        choices=EFFECT_TYPES,
        verbose_name=_('effect type'),
        help_text=_('What type of causal effect is there between the indicators'),
    )

    class Meta:
        abstract = True

    causal_indicator: Any
    effect_indicator: Any

    def __str__(self):
        return '%s %s %s' % (self.causal_indicator, self.effect_type, self.effect_indicator)  # type: ignore


class RelatedIndicator(IndicatorRelationship):
    """A causal relationship between two indicators."""

    HIGH_CONFIDENCE = 'high'
    MEDIUM_CONFIDENCE = 'medium'
    LOW_CONFIDENCE = 'low'
    CONFIDENCE_LEVELS = (
        (HIGH_CONFIDENCE, _('high')),
        (MEDIUM_CONFIDENCE, _('medium')),
        (LOW_CONFIDENCE, _('low')),
    )

    causal_indicator = ParentalKey(
        'indicators.Indicator',
        related_name='related_effects',
        on_delete=models.CASCADE,
        verbose_name=_('causal indicator'),
    )
    effect_indicator = ParentalKey(
        'indicators.Indicator',
        related_name='related_causes',
        on_delete=models.CASCADE,
        verbose_name=_('effect indicator'),
    )
    confidence_level = models.CharField(
        max_length=20,
        choices=CONFIDENCE_LEVELS,
        verbose_name=_('confidence level'),
        help_text=_('How confident we are that the causal effect is present'),
    )

    public_fields: ClassVar = ['id', 'effect_type', 'causal_indicator', 'effect_indicator', 'confidence_level']

    class Meta:
        unique_together = (('causal_indicator', 'effect_indicator'),)
        verbose_name = _('related indicator')
        verbose_name_plural = _('related indicators')

    def __str__(self):
        return '%s %s %s' % (self.causal_indicator, self.effect_type, self.effect_indicator)
