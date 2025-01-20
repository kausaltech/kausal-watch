from __future__ import annotations  # noqa: I001

from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

import reversion
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalManyToManyDescriptor
from reversion.models import Version
from reversion.revisions import _current_frame, add_to_revision, create_revision  # type: ignore
from wagtail.fields import StreamField
from wagtail.blocks.stream_block import StreamValue

from autoslug.fields import AutoSlugField
from sentry_sdk import capture_message

from aplans.utils import PlanRelatedModel

from actions.action_fields import action_registry
from actions.models.action import Action
from actions.models.attributes import Attribute
from pages.models import ActionListPage
from reports.blocks.action_content import ReportFieldBlock

# The following model is for very specialized use and is only imported here so that Django finds it
from reports.spreadsheets.action_print_layout import ReportActionPrintLayoutCustomization  # noqa: F401

from .spreadsheets import ExcelReport
from .types import LiveVersions, SerializedActionVersion

if TYPE_CHECKING:
    from datetime import datetime

    from wagtail.blocks.struct_block import StructValue

    from kausal_common.models.types import FK
    from kausal_common.users import UserOrAnon

    from actions.models import AttributeType, Plan
    from users.models import User


class NoRevisionSave(Exception):
    pass


@reversion.register()
class ReportType(PlanRelatedModel):
    plan: models.ForeignKey[Plan, Plan] = models.ForeignKey('actions.Plan', on_delete=models.CASCADE, related_name='report_types')  # pyright: ignore
    name = models.CharField(max_length=100, verbose_name=_('name'))
    fields = StreamField(block_types=ReportFieldBlock(), null=True, blank=True)

    public_fields = [
        'id', 'plan', 'name', 'reports',
    ]

    class Meta:
        verbose_name = _('report type')
        verbose_name_plural = _('report types')

    @staticmethod
    def generate_for_plan_dashboard(plan: Plan, user: UserOrAnon) -> ReportType:
        report_type = ReportType(plan=plan, name='Dashboard export', fields=None)
        action_list_page = plan.root_page.get_children().type(ActionListPage).get().specific
        dashboard_blocks = [
            (x.block_type, x.value)
            for x in action_list_page.dashboard_columns
        ]
        dashboard_blocks = [
            # filter out non-public attribute fields
            (bt, val) for bt, val in dashboard_blocks
            if bt != 'attribute' or val['attribute_type'].instances_visible_for == 'public'
        ]
        def get_value(field_id: str, value: StructValue) -> StructValue | dict:
            if field_id == 'attribute':
                # Once the report block and the dashboard column block share the implementation,
                # special cases like these can be removed
                return {'attribute_type': value['attribute_type'].pk}
            return action_registry.get_block('report' , field_id).get_default()

        stream_data = [
            {
                'type': f,
                'value': get_value(f, value),
            }
            for f, value in dashboard_blocks
            # TODO: handle these fields in reports by making
            # them blocks that are required
            # (Now they are default fields, always included in reports)
            if f not in ['identifier', 'name']
        ]

        report_type.fields = StreamValue(
            stream_block=report_type.fields.stream_block,
            stream_data=stream_data,
            is_lazy=True,
        )
        return report_type

    def generate_incomplete_report(self) -> Report:
        return Report(
            name='Dashboard export',
            type=self,
            start_date=timezone.now().date(),
            end_date=timezone.now().date(),
            is_complete=False,
            is_public=True,
            fields=None,
        )

    def get_fields_for_type(self, block_type: str) -> list[StreamValue.StreamChild]:
        return [f for f in self.fields if f.block_type == block_type]

    def get_field_labels_for_type(self, block_type: str) -> list[list[str]]:
        fields = self.get_fields_for_type(block_type)
        labels = [field.block.xlsx_column_labels(field.value) for field in fields]
        return labels

    def get_action_list_page(self) -> ActionListPage:
        return self.plan.root_page.get_descendants().live().public().type(ActionListPage).first().specific

    def __str__(self):
        return f'{self.name} ({self.plan.identifier})'


@reversion.register()
class Report(PlanRelatedModel):
    type: FK[ReportType] = models.ForeignKey(ReportType, on_delete=models.CASCADE, related_name='reports')
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

    # Non-persisted fields used only for action dashboard UI reports
    disable_title_sheet: bool
    disable_summary_sheets: bool
    disable_macros: bool

    class Meta:
        verbose_name = _('report')
        verbose_name_plural = _('reports')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disable_title_sheet = False
        self.disable_summary_sheets = False
        self.disable_macros = False

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
        """
        Return action versions and related object versions for an incomplete report.

        The versions are similar to those that would be saved to the database when completing a report.
        """
        if self.is_complete:
            self._raise_complete()

        if ((child_plans := self.type.plan.children.get_queryset().live().values_list('id', flat=True)) and
            # TODO: add .visible_for_user() when it is implemented
                self.type.get_action_list_page().include_related_plans):
            plans = list(child_plans) + [self.type.plan.id]
            actions_to_snapshot = (
                Action.objects.get_queryset().filter(plan__in=plans).visible_for_user(None)
                .prefetch_related(
                    'responsible_parties__organization', 'categories__type', 'choice_attributes__choice',
                    'choice_with_text_attributes__choice', 'text_attributes__type', 'rich_text_attributes__type',
                    'numeric_value_attributes__type', 'category_choice_attributes__type', 'related_indicators',
                    'action_category_through__category',
                )
            )
        else:
            actions_to_snapshot = (
                self.type.plan.actions.get_queryset().visible_for_user(None)
                .prefetch_related(
                    'responsible_parties__organization', 'categories__type', 'choice_attributes__choice',
                    'choice_with_text_attributes__choice', 'text_attributes__type', 'rich_text_attributes__type',
                    'numeric_value_attributes__type', 'category_choice_attributes__type', 'related_indicators',
                    'action_category_through__category',
                )
            )
        result = LiveVersions()

        incomplete_actions = []

        ct = ContentType.objects.get_for_model(Action)
        version_qs = Version.objects.filter(
            content_type=ct,
            object_id__in=[a.pk for a in actions_to_snapshot],
            action_snapshots__report_id=self.pk,
        ).prefetch_related(
            'action_snapshots',
        ).select_related(
            'revision',
        ).order_by(
            '-revision__date_created',
        )
        snapshot_counts = version_qs.annotate(
            snapshot_count=models.Count('action_snapshots')
        ).values('object_id', 'snapshot_count')

        counts_by_action = {
            str(item['object_id']): item['snapshot_count']
            for item in snapshot_counts
        }

        action_snapshots_by_action_pk: dict[int, ActionSnapshot] = dict()
        for version in version_qs:
            action_pk = version.object_id
            if action_pk in action_snapshots_by_action_pk:
                continue
            qs = version.action_snapshots.filter(report_id=self.pk)  # pyright: ignore
            if counts_by_action.get(action_pk, 0) > 1:
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
        """
        Mark this report as complete, as well as all actions that are not yet complete.

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

    def get_related_versions(self) -> models.QuerySet[Version]:
        """
        Get all Version instances from the same revision as this action version's.

        There may be more than one action version in this revision.
        """
        revision = self.action_version.revision
        return revision.version_set.select_related('content_type')

    def get_attribute_for_type_from_versions(
        self, attribute_type: AttributeType, versions: models.QuerySet[Version], ct: ContentType,
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
                Q(serialized_data__contains=str_pattern + ',') | Q(serialized_data__contains=str_pattern + '}'),
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
        """
        Get the first action attribute of the given type in this snapshot.

        Returns None if there is no such attribute.

        Returned model instances have the PK field set, but this does not mean they currently exist in the DB.
        """
        ct = ContentType.objects.get_for_model(Action)
        return self.get_attribute_for_type_from_versions(
            attribute_type, self.get_related_versions(), ct,
        )

    def get_serialized_data(self) -> SerializedActionVersion:
        return SerializedActionVersion.from_version(self.action_version)

    def __str__(self):
        return f'{self.action_version} @ {self.report}'
