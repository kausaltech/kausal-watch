import reversion
import xlsxwriter
from autoslug.fields import AutoSlugField
from contextlib import contextmanager
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from io import BytesIO
from reversion.models import Version
from wagtail.core.fields import StreamField

from actions.models.action import Action
from aplans.utils import PlanRelatedModel
from reports.blocks.action_content import ReportFieldBlock


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

    def __str__(self):
        return f'{self.type.name}: {self.name}'

    def to_xlsx(self):
        output = BytesIO()
        with xlsxwriter.Workbook(output, {'in_memory': True}) as workbook:
            worksheet = workbook.add_worksheet()
            self._write_xlsx_header(worksheet)
            self._write_xlsx_action_rows(workbook, worksheet)
            worksheet.autofit()
            # Set width of some columns explicitly
            worksheet.set_column(0, 0, 20)  # Action
            worksheet.set_column(1, 1, 10)  # Marked as complete by
        return output.getvalue()

    def _write_xlsx_header(self, worksheet: xlsxwriter.Workbook.worksheet_class):
        worksheet.write(0, 0, str(_('Action')))
        worksheet.write(0, 1, str(_('Marked as complete by')))
        worksheet.write(0, 2, str(_('Marked as complete at')))
        column = 3
        for field in self.fields:
            label = field.block.get_report_export_column_label(field.value)
            worksheet.write(0, column, label)
            column += 1

    def _write_xlsx_action_rows(self, workbook: xlsxwriter.Workbook, worksheet: xlsxwriter.Workbook.worksheet_class):
        self._xlsx_cell_format_for_field = {}
        self._xlsx_cell_format_for_date = workbook.add_format({'num_format': 'yyyy-mm-dd h:mm:ss'})
        row = 1
        # For complete reports, we only want to write actions for which we have a snapshot. For incomplete reports, we
        # also want to include the current state of actions for which there is no snapshot.
        if self.is_complete:
            for snapshot in self.action_snapshots.all():
                self._write_xlsx_snapshot_row(workbook, worksheet, snapshot, row)
                row += 1
        else:
            for action in self.type.plan.actions.all():
                try:
                    snapshot = action.get_latest_snapshot(self)
                except ActionSnapshot.DoesNotExist:
                    self._write_xlsx_action_row(workbook, worksheet, action, row)
                else:
                    self._write_xlsx_snapshot_row(workbook, worksheet, snapshot, row)
                row += 1

    def _write_xlsx_snapshot_row(
        self, workbook: xlsxwriter.Workbook, worksheet: xlsxwriter.Workbook.worksheet_class, snapshot, row
    ):
        revision = snapshot.action_version.revision
        # Excel can't handle timezones
        date_created = self.type.plan.to_local_timezone(revision.date_created).replace(tzinfo=None)
        with snapshot.inspect() as action:
            # FIXME: Right now, we print the user who made the last change to the action, which may be different from
            # the user who marked the action as complete.
            self._write_xlsx_action_row(workbook, worksheet, action, row, date_created, revision.user)

    def _write_xlsx_action_row(
        self, workbook: xlsxwriter.Workbook, worksheet: xlsxwriter.Workbook.worksheet_class, action, row,
        completed_at=None, completed_by=None
    ):
        worksheet.write(row, 0, str(action))
        if completed_by:
            worksheet.write(row, 1, str(completed_by))
        if completed_at:
            worksheet.write(row, 2, completed_at, self._xlsx_cell_format_for_date)
        column = 3
        for field in self.fields:
            value = field.block.get_report_export_value_for_action(field.value, action)
            # Add cell format only once per field and cache added formats
            cell_format = self._xlsx_cell_format_for_field.get(field.id)
            if not cell_format:
                cell_format = field.block.add_xlsx_cell_format(field.value, workbook)
                self._xlsx_cell_format_for_field[field.id] = cell_format
            worksheet.write(row, column, value, cell_format)
            column += 1


class ActionSnapshot(models.Model):
    report = models.ForeignKey('reports.Report', on_delete=models.CASCADE, related_name='action_snapshots')
    action_version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name='action_snapshots')

    class Meta:
        verbose_name = _('action snapshot')
        verbose_name_plural = _('action snapshots')
        get_latest_by = 'action_version__revision__date_created'

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
