import reversion
from autoslug.fields import AutoSlugField
from contextlib import contextmanager
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from reversion.models import Version
from wagtail.core.fields import StreamField

from .blocks import ReportFieldBlock
from actions.models.action import Action
from actions.models.plan import Plan
from actions.models.attributes import AttributeType
from aplans.utils import PlanRelatedModel


@reversion.register()
class ReportType(models.Model, PlanRelatedModel):
    plan = models.ForeignKey('actions.Plan', on_delete=models.CASCADE, related_name='report_types')
    name = models.CharField(max_length=100, verbose_name=_('name'))
    fields = StreamField(block_types=ReportFieldBlock(), null=True, blank=True)

    public_fields = [
        'id', 'plan', 'name', 'reports',
    ]

    class Meta:
        verbose_name = _('report type')
        verbose_name_plural = _('report types')

    def create_attribute_types(self, report):
        # Create an attribute type for each block in `fields` that has `attribute_type_format` set
        for field in self.fields:
            attribute_type_format = getattr(field.block, 'attribute_type_format', None)
            if attribute_type_format:
                AttributeType.objects.create(
                    object_content_type=ContentType.objects.get_for_model(Action),
                    scope_content_type=ContentType.objects.get_for_model(Plan),
                    scope_id=report.type.plan.pk,
                    name=field.value['name'],
                    format=attribute_type_format,
                    report=report,
                    report_field=field.id,
                )

    def __str__(self):
        return f'{self.name} ({self.plan.identifier})'


@reversion.register()
class Report(models.Model):
    type = models.ForeignKey(ReportType, on_delete=models.PROTECT, related_name='reports')
    name = models.CharField(max_length=100, verbose_name=_('name'))
    identifier = AutoSlugField(
        always_update=True,
        populate_from='name',
        unique_with='type',
    )
    start_date = models.DateField(verbose_name=_('start date'))
    end_date = models.DateField(verbose_name=_('end date'))
    fields = StreamField(block_types=ReportFieldBlock(), null=True, blank=True)
    is_complete = models.BooleanField(
        default=False, verbose_name=_('complete'),
        help_text=_('Set if report cannot be changed anymore'),
    )
    is_public = models.BooleanField(
        default=False, verbose_name=_('public'),
        help_text=_('Set if report can be shown to the public'),
    )

    public_fields = [
        'type', 'name', 'identifier', 'start_date', 'end_date',
    ]

    class Meta:
        verbose_name = _('report')
        verbose_name_plural = _('reports')

    def save(self, *args, **kwargs):
        is_new_instance = self.pk is None
        super().save(*args, **kwargs)
        if is_new_instance:
            self.type.create_attribute_types(self)

    def __str__(self):
        return f'{self.type.name}: {self.name}'


class ActionSnapshot(models.Model):
    report = models.ForeignKey('reports.Report', on_delete=models.CASCADE, related_name='action_snapshots')
    action_version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name='action_snapshots')

    class Meta:
        verbose_name = _('action snapshot')
        verbose_name_plural = _('action snapshots')

    def __init__(self, *args, action=None, **kwargs):
        if 'action_version' not in kwargs and action is not None:
            kwargs['action_version'] = Version.objects.get_for_object(action).first()
        super().__init__(*args, **kwargs)

    class _RollbackRevision(Exception):
        pass

    @contextmanager
    def inspect(self):
        """
        Use like this to temporarily revert the action to this snapshot:
        with snapshot.inspect() as action:
            pass  # action is reverted here and will be rolled back afterwards
        """
        try:
            with transaction.atomic():
                self.action_version.revision.revert(delete=True)
                yield Action.objects.get(pk=self.action_version.object.pk)
                raise ActionSnapshot._RollbackRevision()
        except ActionSnapshot._RollbackRevision:
            pass

    def __str__(self):
        return f'{self.action_version} @ {self.report}'
