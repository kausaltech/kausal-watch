from __future__ import annotations

import reversion
from autoslug.fields import AutoSlugField
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalManyToManyDescriptor
from reversion.models import Version
from reversion.revisions import _current_frame, add_to_revision, create_revision
from sentry_sdk import capture_message
from typing import TYPE_CHECKING
from wagtail.fields import StreamField
from wagtail.blocks.stream_block import StreamValue

from .spreadsheets import ExcelReport
from aplans.utils import PlanRelatedModel
from actions.models.action import Action
from actions.models.attributes import Attribute
from reports.blocks.action_content import ReportFieldBlock

# The following model is for very specialized use and is only imported here so that Django finds it
from reports.spreadsheets.action_print_layout import ReportActionPrintLayoutCustomization  # noqa: F401


if TYPE_CHECKING:
    from django.db.models.manager import RelatedManager
    from actions.models import AttributeType
    from users.models import User


AttributePath = tuple[int, int, int]


@dataclass
class SerializedVersion:
    type: type
    data: dict
    str: str

    @classmethod
    def from_version(cls, version: Version) -> SerializedVersion:
        return cls(
            type=version.content_type.model_class(),
            data=version.field_dict,
            str=version.object_repr,
        )

    @classmethod
    def from_version_polymorphic(cls, version: Version) -> SerializedVersion:
        model = version.content_type.model_class()
        if issubclass(model, Attribute):
            return SerializedAttributeVersion.from_version(version)
        elif issubclass(model, Action):
            return SerializedActionVersion.from_version(version)
        return cls.from_version(version)


@dataclass
class SerializedAttributeVersion(SerializedVersion):
    attribute_path: AttributePath

    @classmethod
    def from_version(cls, version: Version) -> SerializedAttributeVersion:
        base = SerializedVersion.from_version(version)
        assert issubclass(base.type, Attribute)
        attribute_path = (
            version.field_dict['content_type_id'],
            version.field_dict['object_id'],
            version.field_dict['type_id']
        )
        return cls(
            **asdict(base),
            attribute_path=attribute_path,
        )


@dataclass
class SerializedActionVersion(SerializedVersion):
    completed_at: datetime | None
    completed_by: str | None

    @classmethod
    def from_version(cls, version: Version) -> SerializedActionVersion:
        base = SerializedVersion.from_version(version)
        assert issubclass(base.type, Action)
        completed_at = None
        completed_by = None
        if hasattr(version, 'revision'):
            completed_at = version.revision.date_created
            completed_by = str(version.revision.user) if version.revision.user else ''
        return cls(
            **asdict(base),
            completed_at=completed_at,
            completed_by=completed_by,
        )


@dataclass
class LiveVersions:
    actions: list[Version] = field(default_factory=list)
    related: list[Version] = field(default_factory=list)


class NoRevisionSave(Exception):
    pass


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
    type = models.ForeignKey(ReportType, on_delete=models.CASCADE, related_name='reports')
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
    fields = StreamField(block_types=ReportFieldBlock(), null=True, blank=True)

    public_fields = [
        'type', 'name', 'identifier', 'start_date', 'end_date', 'fields',
    ]

    type: RelatedManager[ReportType]

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

    def get_xlsx_exporter(self) -> ExcelReport:
        self.xlsx_exporter = ExcelReport(self)
        return self.xlsx_exporter

    def _raise_complete(self):
        raise ValueError(_("The report is already marked as complete."))

    def get_live_versions(self) -> LiveVersions:
        """Returns action versions and related object versions for an incomplete report
        similar to those that would be saved to the database when completing a report.
        """
        if self.is_complete:
            self._raise_complete()

        actions_to_snapshot = (
            self.type.plan.actions.visible_for_user(None)
            .prefetch_related(
                'responsible_parties__organization', 'categories__type', 'choice_attributes__choice', 'choice_with_text_attributes__choice',
                'text_attributes__type', 'rich_text_attributes__type', 'numeric_value_attributes__type', 'category_choice_attributes__type',
            )
        )
        result = LiveVersions()

        incomplete_actions = []

        ct = ContentType.objects.get_for_model(Action)
        version_qs = Version.objects.filter(
                content_type=ct,
                object_id__in=[a.pk for a in actions_to_snapshot],
                action_snapshots__report_id=self.pk
            ).prefetch_related(
                'action_snapshots'
            ).select_related(
                'revision'
            ).order_by(
                '-revision__date_created'
            )

        action_snapshots_by_action_pk: dict[int, ActionSnapshot] = dict()
        for version in version_qs:
            action_pk = version.object_id
            if action_pk in action_snapshots_by_action_pk:
                continue
            qs = version.action_snapshots.filter(report_id=self.pk)
            if qs.count() > 1:
                capture_message("Database consistency error: snapshot has multiple versions")
            snapshot = qs.first()
            action_snapshots_by_action_pk[int(action_pk)] = snapshot

        related_versions: set[Version] = set() # non-Action versions from the same revision as any of our actions
        for action in actions_to_snapshot:
            snapshot = action_snapshots_by_action_pk.get(action.pk)
            if snapshot is None:
                incomplete_actions.append(action)
                continue
            result.actions.append(snapshot.action_version)
            related_versions.update(snapshot.get_related_versions())
        fake_revision_versions: list[Version] = []
        try:
            with create_revision(manage_manually=True):
                for action in incomplete_actions:
                    add_to_revision(action)
                fake_revision_versions = list(_current_frame().db_versions['default'].values())
                raise NoRevisionSave()
        except NoRevisionSave:
            pass

        def is_action(v):
            return v._model == Action

        result.actions += filter(is_action, fake_revision_versions)
        result.related = [*related_versions, *filter(lambda v: not is_action(v), fake_revision_versions)]
        # TODO: cleaner way maybe to order by, somehow sort actions
        result.actions = sorted(result.actions, key=lambda x: x.field_dict['order'])
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
        unique_together = (('report', 'action_version'),)

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

    def get_related_versions(self) -> models.QuerySet[Version]:
        """Get all Version instances from the same revision as this action version's.

        There may be more than one action version in this revision.
        """
        revision = self.action_version.revision
        return revision.version_set.select_related('content_type')

    def get_attribute_for_type_from_versions(
        self, attribute_type: AttributeType, versions: models.QuerySet[Version], ct: ContentType
    ) -> models.Model | None:
        # FIXME: This relies on `serialized_data` to contain strings exactly in a certain syntax, which is an
        # implementation detail. Unfortunately, `serialized_data` is not a JSON field, so we can't use Django's
        # QuerySet filter syntax for that.
        # We used to omit the filtering here and filter in Python code in the for loop below, but it's too slow when
        # there are a lot of versions.
        pattern = {
            'type': attribute_type.id,
            'content_type': ct.id,
            'object_id': int(self.action_version.object_id),
        }
        for k, v in pattern.items():
            str_pattern = f'"{k}": {v}'
            versions = versions.filter(
                Q(serialized_data__contains=str_pattern + ',') | Q(serialized_data__contains=str_pattern + '}')
            )
        for version in versions:
            model = version.content_type.model_class()
            # FIXME: It would be safer if there were a common base class for all (and only for) attribute models
            if model.__module__ == 'actions.models.attributes':
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
            attribute_type, self.get_related_versions(), ct
        )

    def get_serialized_data(self) -> SerializedActionVersion:
        return SerializedActionVersion.from_version(self.action_version)

    def __str__(self):
        return f'{self.action_version} @ {self.report}'
