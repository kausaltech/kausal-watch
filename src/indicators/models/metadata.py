from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

import reversion
from django.db import models
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from modeltrans.manager import MultilingualQuerySet

from kausal_common.models.types import manager_from_mlqs

from aplans.utils import IdentifierField, ModificationTracking, TranslatedModelMixin

if TYPE_CHECKING:
    from kausal_common.models.types import MLMM, RevMany

    from indicators.models.common_indicator import CommonIndicator
    from indicators.models.indicator import Indicator


@reversion.register
class Quantity(ClusterableModel, TranslatedModelMixin, ModificationTracking):
    """The quantity that an indicator measures."""

    name = models.CharField(max_length=40, verbose_name=_('name'), unique=True)

    i18n = TranslationField(fields=['name'])

    autocomplete_search_field = 'name'

    objects: ClassVar[MLMM[Self, MultilingualQuerySet[Self]]] = manager_from_mlqs(MultilingualQuerySet[Self])

    # type annotations
    indicators: RevMany[Indicator]
    common_indicators: RevMany[CommonIndicator]

    class Meta:
        verbose_name = pgettext_lazy('physical', 'quantity')
        verbose_name_plural = pgettext_lazy('physical', 'quantities')
        ordering = ('name',)

    def __str__(self):
        return self.get_i18n_value('name')

    def autocomplete_label(self):
        return str(self)


@reversion.register()
class Unit(ClusterableModel, ModificationTracking):
    name = models.CharField(max_length=40, verbose_name=_('name'), unique=True)
    short_name = models.CharField(
        max_length=40,
        null=True,
        blank=True,
        verbose_name=_('short name'),
    )
    verbose_name = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_('verbose name'),
    )
    verbose_name_plural = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name=_('verbose name plural'),
    )

    i18n = TranslationField(
        fields=['name', 'short_name', 'verbose_name', 'verbose_name_plural'],
    )

    objects: ClassVar[MLMM[Self, MultilingualQuerySet[Self]]] = manager_from_mlqs(MultilingualQuerySet[Self])

    autocomplete_search_field = 'name'

    # type annotations
    indicators: RevMany[Indicator]
    common_indicators: RevMany[CommonIndicator]
    name_i18n: str
    short_name_i18n: str
    verbose_name_i18n: str
    verbose_name_plural_i18n: str

    class Meta:
        verbose_name = _('unit')
        verbose_name_plural = _('units')
        ordering = ('name',)

    def __str__(self):
        return self.name

    def autocomplete_label(self):
        return str(self)


class Framework(ClusterableModel):
    identifier = IdentifierField(unique=True)
    name = models.CharField(max_length=200, verbose_name=_('name'))

    i18n = TranslationField(fields=['name'])

    public_fields: ClassVar = ['id', 'name']

    class Meta:
        verbose_name = _('framework')
        verbose_name_plural = _('frameworks')

    def __str__(self):
        return self.name
