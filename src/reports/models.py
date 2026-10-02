from __future__ import annotations  # noqa: I001

from contextlib import contextmanager
from typing import TYPE_CHECKING, ClassVar, Never, Self

import reversion
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
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

from aplans.utils import PlanRelatedModelWithRevision

from actions.action_fields import action_registry
from actions.models.action import Action
from kausal_common.blocks.registry import FieldBlockContext
from reports.blocks.action_content import ReportFieldBlock
from reports.utils import get_field_unique_key

# The following model is for very specialized use and is only imported here so that Django finds it
from reports.spreadsheets.action_print_layout import ReportActionPrintLayoutCustomization  # noqa: F401

from .indicator_data import IndicatorReportData, collect_indicator_report_data
from .spreadsheets import ExcelReport
from .types import LiveVersions, SerializedActionVersion
from actions.models import AttributeType
from indicators.models.action_links import ActionIndicator
from indicators.models.indicator import Indicator

if TYPE_CHECKING:
    from collections.abc import Sequence

    from wagtail.blocks.struct_block import StructValue

    from kausal_common.models.types import FK
    from kausal_common.users import UserOrAnon

    from actions.models import Plan
    from pages.models import ActionListPage
    from users.models import User


class NoRevisionSaveError(Exception):
    pass


class ActionListPageNotFoundError(Exception):
    """Raised when a plan has no live, public ActionListPage (a data-integrity problem)."""

    def __init__(self, plan: Plan):
        self.plan = plan
        super().__init__(f'Plan {plan.identifier!r} has no live, public ActionListPage')


def _attribute_type_visible_in_full_export(attribute_type: AttributeType, user: UserOrAnon, plan: Plan) -> bool:
    visible_for = attribute_type.instances_visible_for
    VisibleFor = AttributeType.VisibleFor
    if visible_for == VisibleFor.PUBLIC:
        return True
    if not user.is_authenticated:
        return False
    if visible_for == VisibleFor.AUTHENTICATED:
        return True
    # Contact-person and moderator visibility depends on the action, and the export has no per-cell
    # filtering, so these columns are only included for plan admins, who see them for every action.
    return user.is_general_admin_for_plan(plan)


@reversion.register()
class ReportType(PlanRelatedModelWithRevision):
    plan: models.ForeignKey[Plan, Plan] = models.ForeignKey('actions.Plan', on_delete=models.CASCADE, related_name='report_types')  # pyright: ignore
    name = models.CharField(max_length=100, verbose_name=_('name'))
    fields: StreamField[StreamValue] = StreamField(block_types=ReportFieldBlock(), null=True, blank=True)  # type: ignore[misc, assignment]  # FIXME: Should not be nullable?
    only_plan_admins_can_mark_actions_as_complete = models.BooleanField(
        default=False,
        verbose_name=_('Only plan admins can mark actions as complete'),
        help_text=_('Only plan admins can mark actions as complete for reports of this type'),
    )
    public_fields: ClassVar[list[str]] = [
        'id',
        'plan',
        'name',
        'reports',
    ]

    id: int

    class Meta:
        verbose_name = _('report type')
        verbose_name_plural = _('report types')

    @staticmethod
    def generate_for_plan_dashboard(plan: Plan, user: UserOrAnon) -> ReportType:
        report_type = ReportType(plan=plan, name='Dashboard export', fields=None)
        action_list_page = report_type.get_action_list_page()
        dashboard_blocks = (
            [(x.block_type, x.value) for x in action_list_page.dashboard_columns] if action_list_page.dashboard_columns else []
        )
        dashboard_blocks = [
            # filter out non-public attribute fields
            (bt, val)
            for bt, val in dashboard_blocks
            if bt != 'attribute' or val['attribute_type'].instances_visible_for == 'public'
        ]

        def get_value(field_id: str, value: StructValue) -> StructValue | dict:
            if field_id == 'attribute':
                # Once the report block and the dashboard column block share the implementation,
                # special cases like these can be removed
                attribute_type = value['attribute_type']
                assert isinstance(attribute_type, AttributeType)
                return {'attribute_type': attribute_type.pk}
            return action_registry.get_block(FieldBlockContext.REPORT, field_id).get_default()

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
        report_type._set_transient_fields(stream_data)
        return report_type

    @staticmethod
    def generate_for_plan_all_fields(plan: Plan, user: UserOrAnon) -> ReportType:
        """
        Build a transient report type with every report field of the plan's actions.

        Attribute types are limited to those whose values the user may see for all actions.
        """
        report_type = ReportType(plan=plan, name='Full export', fields=None)
        assert report_type.fields is not None
        attribute_types = [
            at for at in AttributeType.objects.for_actions(plan) if _attribute_type_visible_in_full_export(at, user, plan)
        ]
        category_types = plan.category_types.filter(usable_for_actions=True)

        stream_data: list[dict] = []
        for field_id in report_type.fields.stream_block.child_blocks:
            if field_id == 'attribute':
                stream_data.extend({'type': field_id, 'value': {'attribute_type': at.pk}} for at in attribute_types)
            elif field_id == 'categories':
                stream_data.extend(
                    {'type': field_id, 'value': {'category_type': ct.pk, 'category_level': None}} for ct in category_types
                )
            else:
                block = action_registry.get_block(FieldBlockContext.REPORT, field_id)
                stream_data.append({'type': field_id, 'value': block.get_default()})
        report_type._set_transient_fields(stream_data)
        return report_type

    def _set_transient_fields(self, stream_data: list[dict]) -> None:
        assert self.fields is not None
        self.fields = StreamValue(
            stream_block=self.fields.stream_block,
            stream_data=stream_data,
            is_lazy=True,
        )

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

    def get_action_list_page(self) -> ActionListPage:
        page = self.plan.get_action_list_page()
        if page is None:
            # Every properly configured plan has a live, public ActionListPage. A plan
            # without one is a data-integrity problem, not a normal runtime condition.
            raise ActionListPageNotFoundError(self.plan)
        return page

    def __str__(self):
        return f'{self.name} ({self.plan.identifier})'

    def clean(self):
        super().clean()

        if not self.fields:
            return

        seen_keys: set[str] = set()
        duplicates: list[str] = []
        for field in self.fields:
            if field is None or field.value is None:
                continue
            field_key = get_field_unique_key(field)
            if field_key in seen_keys:
                duplicates.append(field_key)
            seen_keys.add(field_key)

        if duplicates:
            raise ValidationError({
                'fields': _(
                    'Duplicate fields detected: %(duplicates)s. '
                    'Each field type (attribute type, category type) can only be added once.'
                )
                % {'duplicates': ', '.join(duplicates)}
            })


@reversion.register()
class Report(PlanRelatedModelWithRevision):
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
        default=False,
        verbose_name=_('complete'),
        help_text=_('Set if report cannot be changed anymore'),
    )
    is_public = models.BooleanField(
        default=False,
        verbose_name=_('public'),
        help_text=_('Set if report can be shown to the public'),
    )
    show_in_reporting_tab = models.BooleanField(
        default=True,
        verbose_name=_('Show in reporting tab'),
        help_text=_(
            'Set if the values from this report should be shown in the reporting tab when editing the action. '
            'The values are shown only if this report has been marked as complete.'
        ),
    )

    # The fields are copied from the report type when this report is completed.
    # They are not currently used, but may handle schema-change edge cases later.
    fields: StreamField[StreamValue] = StreamField(block_types=ReportFieldBlock(), null=True, blank=True)  # type: ignore[misc, assignment]  # FIXME: Should not be nullable?

    public_fields: ClassVar[list[str]] = [
        'type',
        'name',
        'identifier',
        'start_date',
        'end_date',
        'fields',
    ]

    # Non-persisted fields used only for action dashboard UI reports
    disable_title_sheet: bool
    disable_summary_sheets: bool
    disable_macros: bool
    disable_indicators_sheet: bool

    class Meta:
        verbose_name = _('report')
        verbose_name_plural = _('reports')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disable_title_sheet = False
        self.disable_summary_sheets = False
        self.disable_macros = False
        self.disable_indicators_sheet = False

    def __str__(self):
        return f'{self.type.name}: {self.name}'

    def get_plans(self):
        return [self.type.plan]

    @classmethod
    def filter_by_plan(cls, plan: Plan, qs: models.QuerySet[Report]) -> models.QuerySet[Report]:
        return qs.filter(type__plan=plan)

    def get_included_plans(self) -> list[Plan]:
        """Return the plan of this report and, if its action list includes related plans, the plan's children."""
        plan = self.type.plan
        children = list(plan.children.all())
        if not children or not self.type.get_action_list_page().include_related_plans:
            return [plan]
        return [plan, *children]

    def get_indicators(self) -> models.QuerySet[Indicator]:
        return Indicator.objects.filter(plans__in=self.get_included_plans()).distinct()

    def collect_indicator_data(self, indicators: Sequence[Indicator]) -> dict[int, IndicatorReportData]:
        plan = self.type.plan
        return collect_indicator_report_data(
            indicators,
            plans=self.get_included_plans(),
            period_start=self.start_date,
            language=plan.primary_language,
        )

    def freeze_indicators_of_action(self, action: Action) -> None:
        """Snapshot the indicators linked to `action`, replacing earlier snapshots of them for this report."""
        indicators = list(self.get_indicators().filter(related_actions__action=action))
        data = self.collect_indicator_data(indicators)
        now = timezone.now()
        IndicatorSnapshot.objects.bulk_create(
            [IndicatorSnapshot(report=self, indicator=i, data=data[i.pk], taken_at=now) for i in indicators],
            update_conflicts=True,
            unique_fields=['report', 'indicator'],
            update_fields=['data', 'taken_at'],
        )

    def unfreeze_indicators_of_action(self, action: Action) -> None:
        """Delete the snapshots of `action`'s indicators unless another action complete for this report links them."""
        complete_actions = Action.objects.get_queryset().complete_for_report(self).exclude(pk=action.pk)
        still_linked = ActionIndicator.objects.filter(action__in=complete_actions).values('indicator_id')
        self.indicator_snapshots.filter(
            indicator__related_actions__action=action,
            created_explicitly=True,
        ).exclude(indicator_id__in=still_linked).delete()

    def get_xlsx_exporter(self, action_ids: list[int] | None = None, user: UserOrAnon | None = None) -> ExcelReport:
        self.xlsx_exporter = ExcelReport(self, action_ids=action_ids, user=user)
        return self.xlsx_exporter

    def _raise_complete(self) -> Never:
        raise ValueError(_('The report is already marked as complete.'))

    def get_live_versions(self, action_ids: list[int] | None = None, user: UserOrAnon | None = None) -> LiveVersions:  # noqa: C901
        """
        Return action versions and related object versions for an incomplete report.

        The versions are similar to those that would be saved to the database when completing a report.

        If `action_ids` is not None, the included actions are restricted to those with the given IDs.

        Only plans and actions visible to `user` are included; `None` means an anonymous viewer.
        """
        if self.is_complete:
            self._raise_complete()

        if (
            child_plans := self.type.plan.children.get_queryset().visible_for_user(user).values_list('id', flat=True)
        ) and self.type.get_action_list_page().include_related_plans:
            plans = list(child_plans) + [self.type.plan.id]
            actions_to_snapshot = (
                Action.objects
                .get_queryset()
                .filter(plan__in=plans)
                .visible_for_user(user)
                .prefetch_related(
                    'responsible_parties__organization',
                    # Reversion follows these from every task, and names each one through `__str__`,
                    # so the assignees come along too.
                    'tasks__responsible_parties__organization',
                    'tasks__contact_persons__person',
                    'categories__type',
                    'choice_attributes__choice',
                    'choice_with_text_attributes__choice',
                    'text_attributes__type',
                    'rich_text_attributes__type',
                    'numeric_value_attributes__type',
                    'category_choice_attributes__type',
                    'related_indicators',
                    'action_category_through__category',
                )
            ).order_by('plan', 'order')
        else:
            actions_to_snapshot = (
                self.type.plan.actions
                .get_queryset()
                .visible_for_user(user)
                .prefetch_related(
                    'responsible_parties__organization',
                    # Reversion follows these from every task, and names each one through `__str__`,
                    # so the assignees come along too.
                    'tasks__responsible_parties__organization',
                    'tasks__contact_persons__person',
                    'categories__type',
                    'choice_attributes__choice',
                    'choice_with_text_attributes__choice',
                    'text_attributes__type',
                    'rich_text_attributes__type',
                    'numeric_value_attributes__type',
                    'category_choice_attributes__type',
                    'related_indicators',
                    'action_category_through__category',
                )
            ).order_by('order')
        if action_ids is not None:
            actions_to_snapshot = actions_to_snapshot.filter(id__in=action_ids)
        result = LiveVersions()

        incomplete_actions: list[Action] = []

        ct = ContentType.objects.get_for_model(Action)
        version_qs = Version.objects.filter(
            content_type=ct,
            object_id__in=[a.pk for a in actions_to_snapshot],
            action_snapshots__report_id=self.pk,
        )

        # Fetch all relevant ActionSnapshots in a single query
        all_snapshots = (
            ActionSnapshot.objects
            .filter(action_version__in=version_qs, report_id=self.pk)
            .select_related(
                'action_version__revision',
            )
            .order_by(
                '-action_version__revision__date_created',
            )
        )

        snapshot_counts = (
            all_snapshots
            .values('action_version__object_id')
            .annotate(snapshot_count=models.Count('id'))
            .values('action_version__object_id', 'snapshot_count')
        )

        counts_by_action = {str(item['action_version__object_id']): item['snapshot_count'] for item in snapshot_counts}

        action_snapshots_by_action_pk: dict[int, ActionSnapshot] = dict()

        for snapshot in all_snapshots:
            action_pk = snapshot.action_version.object_id
            if action_pk not in action_snapshots_by_action_pk:
                action_snapshots_by_action_pk[int(action_pk)] = snapshot
                if counts_by_action.get(action_pk, 0) > 1:
                    capture_message('Database consistency error: snapshot has multiple versions')

        related_versions: set[Version] = set()  # non-Action versions from the same revision as any of our actions

        for action in actions_to_snapshot:
            snapshot = action_snapshots_by_action_pk.get(action.pk)  # type: ignore[assignment]
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
                raise NoRevisionSaveError()  # noqa: TRY301
        except NoRevisionSaveError:
            pass

        def is_action(v: Version) -> bool:
            return v._model == Action

        result.actions += filter(is_action, fake_revision_versions)
        result.related = [*related_versions, *filter(lambda v: not is_action(v), fake_revision_versions)]
        return result

    def mark_as_complete(self, user: User):
        """
        Mark this report as complete, as well as all actions that are not yet complete.

        The snapshots for actions that are marked as complete by this will have `created_explicitly` set to False.
        """
        if self.is_complete:
            self._raise_complete()
        actions_to_snapshot = self.type.plan.actions.exclude(
            id__in=Action.objects.get_queryset().complete_for_report(self),
        ).prefetch_related(
            # Reversion follows these from every task while the revision is built, and names each one
            # through `__str__`, so the assignees come along too.
            'tasks__responsible_parties__organization',
            'tasks__contact_persons__person',
        )
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

        indicators = list(self.get_indicators().exclude(report_snapshots__report=self))
        data = self.collect_indicator_data(indicators)
        IndicatorSnapshot.objects.bulk_create(
            IndicatorSnapshot(report=self, indicator=i, data=data[i.pk], created_explicitly=False) for i in indicators
        )

    def undo_marking_as_complete(self, user):
        if not self.is_complete:
            raise ValueError(_('The report is not marked as complete.'))
        with reversion.create_revision():
            reversion.set_comment(_("Undid marking report '%s' as complete") % self)
            reversion.set_user(user)
            self.is_complete = False
            self.save()
            self.action_snapshots.filter(created_explicitly=False).delete()
            self.indicator_snapshots.filter(created_explicitly=False).delete()


class ActionSnapshot(models.Model):
    report = models.ForeignKey('reports.Report', on_delete=models.CASCADE, related_name='action_snapshots')
    action_version = models.ForeignKey(Version, on_delete=models.CASCADE, related_name='action_snapshots')
    created_explicitly = models.BooleanField(default=True)

    class Meta:
        verbose_name = _('action snapshot')
        verbose_name_plural = _('action snapshots')
        get_latest_by = 'action_version__revision__date_created'
        unique_together = (('report', 'action_version'),)

    def __str__(self):
        return f'{self.action_version} @ {self.report}'

    @classmethod
    def for_action(cls, report: Report, action: Action, created_explicitly: bool = True) -> ActionSnapshot:
        action_version: Version = Version.objects.get_for_object(action).first()
        return cls(report=report, action_version=action_version, created_explicitly=created_explicitly)

    class _RollbackRevisionError(Exception):
        pass

    @contextmanager
    def inspect(self):
        """
        Temporarily revert the action to this snapshot as follows.

        with snapshot.inspect() as action:
            pass  # action is reverted here and will be rolled back afterwards.
        """
        try:
            with transaction.atomic():
                self.action_version.revision.revert(delete=True)
                yield Action.objects.get(pk=self.action_version.object.pk)
                raise ActionSnapshot._RollbackRevisionError()  # noqa: TRY301
        except ActionSnapshot._RollbackRevisionError:
            pass

    def get_related_versions(self) -> models.QuerySet[Version]:
        """
        Get all Version instances from the same revision as this action version's.

        There may be more than one action version in this revision.
        """
        revision = self.action_version.revision
        return revision.version_set.select_related('content_type')

    def get_attribute_for_type_from_versions(
        self,
        attribute_type: AttributeType,
        versions: models.QuerySet[Version],
        ct: ContentType,
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
                for field_name, serialized_value in version.field_dict.items():
                    value = serialized_value
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

    def get_attribute_for_type(self, attribute_type: AttributeType):
        """
        Get the first action attribute of the given type in this snapshot.

        Returns None if there is no such attribute.

        Returned model instances have the PK field set, but this does not mean they currently exist in the DB.
        """
        ct = ContentType.objects.get_for_model(Action)
        return self.get_attribute_for_type_from_versions(
            attribute_type,
            self.get_related_versions(),
            ct,
        )

    def get_serialized_data(self) -> SerializedActionVersion:
        return SerializedActionVersion.from_version(self.action_version)


class IndicatorSnapshot(models.Model):
    """The data of an indicator at the time an action linked to it, or the whole report, was marked as complete."""

    report: FK[Report] = models.ForeignKey(Report, on_delete=models.CASCADE, related_name='indicator_snapshots')
    indicator: FK[Indicator] = models.ForeignKey(
        'indicators.Indicator', on_delete=models.CASCADE, related_name='report_snapshots'
    )
    indicator_id: int
    data: models.JSONField[IndicatorReportData] = models.JSONField()
    created_explicitly = models.BooleanField(default=True)
    taken_at = models.DateTimeField(default=timezone.now)

    objects: ClassVar[models.Manager[Self]]

    class Meta:
        verbose_name = _('indicator snapshot')
        verbose_name_plural = _('indicator snapshots')
        constraints = [
            models.UniqueConstraint(fields=['report', 'indicator'], name='unique_indicator_snapshot_per_report'),
        ]

    def __str__(self):
        return f'{self.indicator} @ {self.report}'
