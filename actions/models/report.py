import reversion
from django.db import models
from django.utils.translation import gettext_lazy as _
from wagtail.core.fields import StreamField

from actions.blocks import ReportFieldBlock
from aplans.utils import IdentifierField, PlanRelatedModel


@reversion.register()
class ReportType(models.Model, PlanRelatedModel):
    plan = models.ForeignKey('actions.Plan', on_delete=models.CASCADE, related_name='report_types')
    name = models.CharField(max_length=100, verbose_name=_('name'))
    fields = StreamField(block_types=ReportFieldBlock(), null=True, blank=True)

    def __str__(self):
        return f'{self.name} ({self.plan.identifier})'


@reversion.register()
class Report(models.Model):
    type = models.ForeignKey(ReportType, on_delete=models.CASCADE, related_name='reports')
    # fields = StreamField(block_types=ReportFieldBlock(), null=True, blank=True)
    name = models.CharField(max_length=100, verbose_name=_('name'))
    identifier = IdentifierField()  # needed to create identifiers for new attribute types
    start_date = models.DateField(verbose_name=_('start date'))
    end_date = models.DateField(verbose_name=_('end date'))
    is_complete = models.BooleanField(
        default=False, verbose_name=_('complete'),
        help_text=_('Set if report cannot be changed anymore'),
    )
    is_public = models.BooleanField(
        default=False, verbose_name=_('is public'),
        help_text=_('Set if report can be shown to the public'),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['type', 'identifier'],
                name='unique_identifier_per_report_type',
            ),
        ]

    def __str__(self):
        return self.name
