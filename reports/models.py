from __future__ import annotations

import typing
from typing import TYPE_CHECKING
from contextlib import contextmanager

import reversion
from autoslug.fields import AutoSlugField
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalManyToManyDescriptor
from reversion.models import Version
from reversion.revisions import _current_frame, add_to_revision, create_revision
from wagtail.fields import StreamField
from wagtail.blocks.stream_block import StreamValue

from actions.models.action import Action
from aplans.utils import PlanRelatedModel
from reports.blocks.action_content import ReportFieldBlock

from .spreadsheets import ExcelReport
from .utils import group_by_model, prepare_serialized_model_version

if TYPE_CHECKING:
    from actions.models import AttributeType
    from users.models import User

class NoRevisionSave(Exception):
    pass


@reversion.register()
class ReportType(models.Model, PlanRelatedModel):
    plan = models.ForeignKey('actions.Plan', on_delete=models.CASCADE, related_name='report_types')
    name = models.CharField(max_length=100, verbose_name=_('name'))
    fields = StreamField(block_types=ReportFieldBlock(), null=True, blank=True, use_json_field=True)

    public_fields = [
        'id', 'plan', 'name', 'reports',
    ]

    class Meta:
        verbose_name = _('report type')
        verbose_name_plural = _('report types')

    def get_fields_for_type(self, block_type: str) -> list[StreamValue.StreamChild]:
        return [f for f in self.fields if f.block_type == block_type]

    def get_field_labels_for_type(self, block_type: str) -> list[list[str]]:
        fields = self.get_fields_for_type(block_type)
        labels = [field.block.xlsx_column_labels(field.value) for field in fields]
        return labels

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
    is_complete = models.BooleanField(
        default=False, verbose_name=_('complete'),
        help_text=_('Set if report cannot be changed anymore'),
    )
    is_public = models.BooleanField(
        default=False, verbose_name=_('public'),
        help_text=_('Set if report can be shown to the public'),
    )

    # The fields are copied from the report type at the time of completion of this report. These are not currently used anywhere but we
    # might need them in the future to take care of certain edge cases wrt. schema changes
    fields = StreamField(block_types=ReportFieldBlock(), null=True, blank=True, use_json_field=True)

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
        self.xlsx_exporter = xlsx_exporter
        return xlsx_exporter.generate_xlsx()

    def _raise_complete(self):
        raise ValueError(_("The report is already marked as complete."))

    def get_live_action_versions(self) -> list[tuple[Version, list[Version], dict]]:
        """Returns action versions for an incomplete report
        similar to those that would be saved to the database when completing a report.
        """
        if self.is_complete:
            self._raise_complete()

        actions_to_snapshot = (
            self.type.plan.actions.all()
            .prefetch_related('responsible_parties__organization', 'categories__type')
        )
        result = list()

        def is_action(v):
            return v._model == Action

        incomplete_actions = []
        ct = ContentType.objects.get_for_model(Action)
        for action in actions_to_snapshot:
            try:
                snapshot = action.get_latest_snapshot(report=self)
                revision = snapshot.action_version.revision
                result.append((snapshot.action_version, snapshot.get_related_versions(ct),
                               {'completed_at': revision.date_created,
                                'completed_by': str(revision.user) if revision.user else ''}))
                continue
            except ObjectDoesNotExist:
                incomplete_actions.append(action)
        versions = []
        try:
            with create_revision(manage_manually=True):
                for action in incomplete_actions:
                    add_to_revision(action)
                versions = list(_current_frame().db_versions['default'].values())
                raise NoRevisionSave()
        except NoRevisionSave:
            pass
        action_versions = list(filter(is_action, versions))
        related_versions = list(filter(lambda v: not is_action(v), versions))
        for action_version in action_versions:
            result.append((action_version, related_versions,
                           {'completed_at': None,
                            'completed_by': None}))
        return result

    def mark_as_complete(self, user: User):
        """Mark this report as complete, as well as all actions that are not yet complete.

        The snapshots for actions that are marked as complete by this will have `created_explicitly` set to False.
        """
        if self.is_complete:
            self._raise_complete()
        actions_to_snapshot = self.type.plan.actions.exclude(id__in=Action.objects.get_queryset().complete_for_report(self))
        with reversion.create_revision():
            reversion.set_comment(_("Marked report '%s' as complete") % self)
            reversion.set_user(user)
            self.is_complete = True
            self.fields = self.type.fields
            self.save()
            for action in actions_to_snapshot:
                # Create snapshot for this action after revision is created to get the resulting version
                reversion.add_to_revision(action)

        for action in actions_to_snapshot:
            ActionSnapshot.for_action(
                report=self,
                action=action,
                created_explicitly=False,
            ).save()

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

    @classmethod
    def for_action(cls, report: Report, action: Action, created_explicitly: bool = True) -> ActionSnapshot:
        action_version: Version = Version.objects.get_for_object(action).first()
        return cls(report=report, action_version=action_version, created_explicitly=created_explicitly)

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

    def get_related_versions(self, ct) -> models.QuerySet[Version]:
        return self.action_version.revision.version_set.exclude(content_type=ct).select_related('content_type')

    def get_attribute_for_type_from_versions(
        self, attribute_type: AttributeType, versions: typing.Iterable[Version], ct: ContentType
    ) -> models.Model | None:
        pattern = {
            'type_id': attribute_type.id,
            'content_type_id': ct.id,
            'object_id': int(self.action_version.object_id),
        }

        for version in versions:
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
                        value = [related_model.objects.get(pk=pk) for pk in value]  # type: ignore[attr-defined]
                    field_dict[field_name] = value
                # This does not work for model fields that are a ManyToManyDescriptor. In such cases, you may want
                # to make the model a ClusterableModel and use, e.g., ParentalManyToManyField instead of
                # ManyToManyField.
                instance = model(**field_dict)
                return instance
        return None

    def get_attribute_for_type(self, attribute_type):
        """Get the first action attribute of the given type in this snapshot.

        Returns None if there is no such attribute.

        Returned model instances have the PK field set, but this does not mean they currently exist in the DB.
        """
        ct = ContentType.objects.get_for_model(Action)
        return self.get_attribute_for_type_from_versions(
            attribute_type, self.get_related_versions(ct), ct
        )

    def get_related_serialized_data(self):
        ct = ContentType.objects.get_for_model(Action)
        all_related_versions = self.get_related_versions(ct)
        revision = self.action_version.revision
        action = prepare_serialized_model_version(self.action_version)
        related_objects = group_by_model([prepare_serialized_model_version(o) for o in all_related_versions])
        return dict(
            action=action,
            related_objects=related_objects,
            completion={
                'completed_at': revision.date_created,
                'completed_by': str(revision.user)
            }
        )

    def __str__(self):
        return f'{self.action_version} @ {self.report}'
