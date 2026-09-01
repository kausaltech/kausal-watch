from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from collections.abc import Callable


class IndicatorValuesImportLog(models.Model):
    """A record of a succesful importing of indicator values."""

    get_source_system_display: Callable[[], str]

    SOURCE_SYSTEM_KAUSAL_PATHS = 'kausal_paths'
    SOURCE_SYSTEM_CHOICES = [
        (SOURCE_SYSTEM_KAUSAL_PATHS, _('Kausal Paths')),
    ]

    indicator = models.ForeignKey('indicators.Indicator', on_delete=models.CASCADE, related_name='values_import_logs')
    source_system = models.CharField(max_length=50, choices=SOURCE_SYSTEM_CHOICES)
    source_url = models.URLField()
    import_parameters = models.JSONField(default=dict, blank=True)
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['imported_at']
        verbose_name = _('Indicator values import log')
        verbose_name_plural = _('Indicator values import logs')

    def __str__(self) -> str:
        return f'{self.indicator} - {self.get_source_system_display()} - {self.imported_at}'
