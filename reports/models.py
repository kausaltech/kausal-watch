from autoslug.fields import AutoSlugField
from contextlib import contextmanager
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from io import BytesIO
from reversion.models import Version
from wagtail.core.fields import StreamField
import reversion
import xlsxwriter

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
        'type', 'name', 'identifier', 'start_date', 'end_date', 'fields',
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
                self._write_xlsx_action_row(workbook, worksheet, snapshot, row)
                row += 1
        else:
            for action in self.type.plan.actions.all():
                try:
                    snapshot = action.get_latest_snapshot(self)
                except ActionSnapshot.DoesNotExist:
                    self._write_xlsx_action_row(workbook, worksheet, action, row)
                else:
                    self._write_xlsx_action_row(workbook, worksheet, snapshot, row)
                row += 1

    def _write_xlsx_action_row(
        self, workbook: xlsxwriter.Workbook, worksheet: xlsxwriter.Workbook.worksheet_class, action_or_snapshot, row,
    ):
        # FIXME: action_or_snapshot can be an Action or ActionSnapshot, but distinguishing the cases is ugly. Improve.
        if isinstance(action_or_snapshot, ActionSnapshot):
            # Instead of fucking around with the `name` and `i18n` fields to simulate `name_i18n`, just build a fake
            # model instance
            field_dict = action_or_snapshot.action_version.field_dict
            action_name = str(Action(name=field_dict['name'], plan_id=field_dict['plan_id'], i18n=field_dict['i18n']))
            # Get creation date and user from the version's revision
            revision = action_or_snapshot.action_version.revision
            # Excel can't handle timezones
            completed_at = self.type.plan.to_local_timezone(revision.date_created).replace(tzinfo=None)
            completed_by = revision.user
            # FIXME: Right now, we print the user who made the last change to the action, which may be different from
            # the user who marked the action as complete.
        else:
            assert isinstance(action_or_snapshot, Action)
            action_name = str(action_or_snapshot)
            completed_at = None
            completed_by = None
        worksheet.write(row, 0, action_name)
        if completed_by:
            worksheet.write(row, 1, str(completed_by))
        if completed_at:
            worksheet.write(row, 2, completed_at, self._xlsx_cell_format_for_date)
        column = 3
        for field in self.fields:
            if isinstance(action_or_snapshot, ActionSnapshot):
                value = field.block.get_report_export_value_for_action_snapshot(field.value, action_or_snapshot)
            else:
                value = field.block.get_report_export_value_for_action(field.value, action_or_snapshot)
            # Add cell format only once per field and cache added formats
            cell_format = self._xlsx_cell_format_for_field.get(field.id)
            if not cell_format:
                cell_format = field.block.add_xlsx_cell_format(field.value, workbook)
                self._xlsx_cell_format_for_field[field.id] = cell_format
            worksheet.write(row, column, value, cell_format)
            column += 1

    def mark_as_complete(self, user):
        """Mark this report as complete, as well as all actions that are not yet complete.

        The snapshots for actions that are marked as complete by this will have `created_explicitly` set to False.
        """
        if self.is_complete:
            raise ValueError(_("The report is already marked as complete."))
        actions_to_snapshot = self.type.plan.actions.exclude(id__in=Action.objects.complete_for_report(self))
        with reversion.create_revision():
            reversion.set_comment(_("Marked report '%s' as complete") % self)
            reversion.set_user(user)
            self.is_complete = True
            self.save()
            for action in actions_to_snapshot:
                # Create snapshot for this action after revision is created to get the resulting version
                reversion.add_to_revision(action)
        for action in actions_to_snapshot:
            ActionSnapshot.objects.create(
                report=self,
                action=action,
                created_explicitly=False,
            )

    def undo_marking_as_complete(self, user):
        if not self.is_complete:
            raise ValueError(_("The report is not marked as complete."))
        with reversion.create_revision():
            reversion.set_comment(_("Undid marking report '%s' as complete") % self)
            reversion.set_user(user)
            self.is_complete = False
            self.save()
            self.action_snapshots.filter(created_explicitly=False).delete()


class ActionSnapshot(models.Model):
    report = models.ForeignKey('reports.Report', on_delete=models.CASCADE, related_name='action_snapshots')
    action_version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name='action_snapshots')
    created_explicitly = models.BooleanField(default=True)

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
        """Use like this to temporarily revert the action to this snapshot:
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

    def get_attribute_for_type(self, attribute_type):
        """Get the first action attribute of the given type in this snapshot.

        Returns None if there is no such attribute.

        Returned model instances have the PK field set, but this does not mean they currently exist in the DB.
        """
        pattern = {
            'type_id': attribute_type.id,
            'content_type_id': ContentType.objects.get_for_model(Action).id,
            'object_id': int(self.action_version.object_id),
        }
        for version in self.action_version.revision.version_set.all():
            if all(version.field_dict.get(key) == value for key, value in pattern.items()):
                model = version.content_type.model_class()
                return model(**version.field_dict)
        return None

    def __str__(self):
        return f'{self.action_version} @ {self.report}'
