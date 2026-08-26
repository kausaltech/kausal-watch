from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Unpack

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail.models import Page
from wagtail.models.audit_log import BaseLogEntry, BaseLogEntryManager, LogEntryQuerySet

from kausal_common.users import user_or_none

from pages.models import AplansPage
from users.models import User

if TYPE_CHECKING:
    from collections.abc import Sequence

    from wagtail.models.audit_log import LogActionArgs

    from kausal_common.models.types import FK

    from aplans.utils import IndirectPlanRelatedModel, PlanRelatedModel

    from actions.models import Plan

type PlanScopedPageModel = AplansPage
type PlanScopedModel = PlanRelatedModel | IndirectPlanRelatedModel


class PlanScopedModelLogEntryManager(
    BaseLogEntryManager['PlanScopedModelLogEntry', LogEntryQuerySet['PlanScopedModelLogEntry'], PlanScopedModel, User]
):
    def log_bulk_action[M: PlanScopedModel](
        self, plan: Plan, instances: Sequence[M], action: str, **kwargs: Unpack[LogActionArgs[User]]
    ) -> list[PlanScopedModelLogEntry]:
        if len(instances) == 0:
            return []
        kwargs['data'] = kwargs.get('data') or {}
        label = kwargs.pop('title', None)
        kwargs['timestamp'] = kwargs.get('timestamp', timezone.now())
        content_type = ContentType.objects.get_for_model(instances[0], for_concrete_model=False)
        log_entries: list[PlanScopedModelLogEntry] = []
        for instance in instances:
            if instance.pk is None:
                raise ValueError('Attempted to log an action for object %r with empty primary key' % (instance,))
            log_entries.append(
                PlanScopedModelLogEntry(
                    content_type=content_type,
                    label=label or str(instance),
                    action=action,
                    plan_id=plan.pk,
                    object_id=str(instance.pk),
                    **kwargs,
                )
            )
        return PlanScopedModelLogEntry.objects.bulk_create(log_entries)

    def log_action(
        self,
        instance: PlanScopedModel,
        action: str,
        **kwargs: Unpack[LogActionArgs],
    ) -> PlanScopedModelLogEntry | None:
        if instance.pk is None:
            raise ValueError('Attempted to log an action for object %r with empty primary key' % (instance,))

        kwargs['data'] = kwargs.get('data') or {}
        title = kwargs.pop('title', None)
        if not title:
            title = self.get_instance_title(instance)

        kwargs['timestamp'] = kwargs.get('timestamp', timezone.now())
        object_id = str(instance.pk)

        user = user_or_none(kwargs.get('user'))
        plans = instance.get_plans()
        retval = None
        if not plans and user is not None:
            plans = [user.get_active_admin_plan()]
        for plan in set(plans):
            retval = PlanScopedModelLogEntry.objects.create(
                content_type=ContentType.objects.get_for_model(instance, for_concrete_model=False),
                label=title,
                action=action,
                object_id=object_id,
                plan=plan,
                **kwargs,
            )
        return retval

    def viewable_by_user(self, user: User):  # type: ignore[override]
        return super().viewable_by_user(user).filter(plan__isnull=False, plan__in=user.get_adminable_plans())

    def for_instance(self, instance: PlanScopedModel):
        return self.filter(
            content_type=ContentType.objects.get_for_model(instance, for_concrete_model=False),
            object_id=str(instance.pk),
        )


class PlanScopedModelLogEntry(BaseLogEntry[User]):
    # The type error below stems from the Wagtail code
    object_id: models.CharField[str, str] = models.CharField(max_length=255, blank=False, db_index=True)
    plan: FK[Plan] = models.ForeignKey('actions.Plan', null=False, blank=False, on_delete=models.PROTECT)

    objects: ClassVar[PlanScopedModelLogEntryManager] = PlanScopedModelLogEntryManager()

    class Meta:
        ordering = ['-timestamp', '-id']
        verbose_name = _('plan-scoped model log entry')
        verbose_name_plural = _('plan-scoped model log entries')

    def __str__(self) -> str:
        return f"PlanScopedModelLogEntry {self.pk}: '{self.action}' on '{self.object_verbose_name()}' with id {self.object_id}"


class PlanScopedPageLogEntryQuerySet(LogEntryQuerySet['PlanScopedPageLogEntry']):
    if TYPE_CHECKING:

        @classmethod
        def as_manager(cls) -> models.Manager[PlanScopedPageLogEntry]: ...  # type: ignore[override]

    def get_content_type_ids(self):
        if self.exists():
            return {ContentType.objects.get_for_model(Page).pk}
        return set()

    def filter_on_content_type(self, content_type):
        if content_type == ContentType.objects.get_for_model(Page):
            return self
        return self.none()


class PlanScopedPageLogEntryManager(
    BaseLogEntryManager['PlanScopedPageLogEntry', PlanScopedPageLogEntryQuerySet, AplansPage, User]
):
    def get_queryset(self):
        return PlanScopedPageLogEntryQuerySet(self.model, using=self._db)

    def get_instance_title(self, instance: AplansPage) -> str:
        return instance.specific_deferred.get_admin_display_title()

    def log_action(
        self,
        instance: AplansPage,
        action: str,
        /,
        plan: Plan | None = None,
        page: Page | None = None,
        **kwargs: Unpack[LogActionArgs],
    ) -> PlanScopedPageLogEntry | None:
        plan = instance.plan
        if plan is None:
            return None

        if instance.pk is None:
            raise ValueError('Attempted to log an action for object %r with empty primary key' % (instance,))

        kwargs['data'] = kwargs.get('data') or {}
        title = kwargs.pop('title', None)
        if not title:
            title = self.get_instance_title(instance)

        kwargs['timestamp'] = kwargs.get('timestamp', timezone.now())

        return PlanScopedPageLogEntry.objects.create(
            content_type=ContentType.objects.get_for_model(instance, for_concrete_model=False),
            label=title,
            action=action,
            page=instance,
            plan=plan,
            **kwargs,
        )

    def viewable_by_user(self, user: User):
        from django.db.models import Q, Subquery
        from wagtail.permissions import page_permission_policy

        explorable_instances = page_permission_policy.explorable_instances(user)
        q = Q(page__in=explorable_instances.values_list('pk', flat=True))

        root_page = Page.get_first_root_node()
        if root_page is None:
            raise ValueError('No root page found')
        root_page_permissions = root_page.permissions_for_user(user)
        if user.is_superuser or root_page_permissions.can_add_subpage() or root_page_permissions.can_edit():
            q = q | Q(page_id__in=Subquery(PlanScopedPageLogEntry.objects.filter(deleted=True).values('page_id')))

        return PlanScopedPageLogEntry.objects.filter(q).filter(plan__isnull=False, plan__in=user.get_adminable_plans())

    def for_instance(self, instance: AplansPage):
        return self.filter(page=instance)


class PlanScopedPageLogEntry(BaseLogEntry[User]):
    page: FK[Page] = models.ForeignKey(
        'wagtailcore.Page',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='+',
    )
    plan: FK[Plan] = models.ForeignKey('actions.Plan', null=False, blank=False, on_delete=models.PROTECT)
    page_id: int

    objects: ClassVar[PlanScopedPageLogEntryManager] = PlanScopedPageLogEntryManager()

    class Meta:
        ordering = ['-timestamp', '-id']
        verbose_name = _('plan-scoped page log entry')
        verbose_name_plural = _('plan-scoped page log entries')

    def __str__(self):
        return "PlanScopedPageLogEntry %d: '%s' on '%s' with id %s" % (
            self.pk,
            self.action,
            self.object_verbose_name(),
            self.page_id,
        )

    @cached_property
    def object_id(self):
        return self.page_id

    @cached_property
    def message(self):
        if self.action == 'wagtail.edit':
            return _('Draft saved')
        return super().message
