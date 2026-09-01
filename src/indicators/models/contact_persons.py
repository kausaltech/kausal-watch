from __future__ import annotations

from typing import TYPE_CHECKING, Self

from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey

from aplans.utils import OrderedModel

if TYPE_CHECKING:
    from modelcluster.fields import PK

    from people.models import Person


class IndicatorContactPerson(OrderedModel):
    """Contact person for an indicator."""

    indicator = ParentalKey(
        'indicators.Indicator',
        on_delete=models.CASCADE,
        verbose_name=_('indicator'),
        related_name='contact_persons',
    )
    person: PK[Person] = ParentalKey(
        'people.Person',
        on_delete=models.CASCADE,
        verbose_name=_('person'),
    )

    indicator_id: int
    person_id: int

    def filter_siblings(self, qs: models.QuerySet[Self]) -> models.QuerySet[Self]:
        return qs.filter(indicator=self.indicator)

    class Meta:
        ordering = ['indicator', 'order']
        indexes = [
            models.Index(fields=['indicator', 'order']),
        ]
        unique_together = (('indicator', 'person'),)
        verbose_name = _('indicator contact person')
        verbose_name_plural = _('indicator contact persons')

    def __str__(self):
        return str(self.person)
