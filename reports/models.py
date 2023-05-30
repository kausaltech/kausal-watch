from autoslug.fields import AutoSlugField
from contextlib import contextmanager
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalManyToManyDescriptor
from reversion.models import Version
from wagtail.core.fields import StreamField
import reversion

from actions.models.action import Action
from aplans.utils import PlanRelatedModel
from reports.blocks.action_content import ReportFieldBlock
from .spreadsheets import ExcelReport


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
class Report(models.Model, PlanRelatedModel):
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

    def get_plans(self):
        return [self.type.plan]

    @classmethod
    def filter_by_plan(cls, plan, qs):
        return qs.filter(type__plan=plan)

    def to_xlsx(self):
        xlsx_exporter = ExcelReport(self)
        return xlsx_exporter.generate_xlsx()

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
            model = version.content_type.model_class()
            # FIXME: It would be safer if there were a common base class for all (and only for) attribute models
            if (model.__module__ == 'actions.models.attributes'
                    and all(version.field_dict.get(key) == value for key, value in pattern.items())):
                # Replace PKs by model instances. (We assume they still exist in the DB, otherwise we are fucked.)
                field_dict = {}
                for field_name, value in version.field_dict.items():
                    field = getattr(model, field_name)
                    if isinstance(field, ParentalManyToManyDescriptor):
                        # value should be a list of PKs of the related model; transform it to a list of instances
                        related_model = field.rel.model
                        value = [related_model.objects.get(pk=pk) for pk in value]
                    field_dict[field_name] = value
                # This does not work for model fields that are a ManyToManyDescriptor. In such cases, you may want
                # to make the model a ClusterableModel and use, e.g., ParentalManyToManyField instead of
                # ManyToManyField.
                instance = model(**field_dict)
                return instance
        return None

    def __str__(self):
        return f'{self.action_version} @ {self.report}'
