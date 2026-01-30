from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail.models import Page
from wagtail.models.audit_log import BaseLogEntry, BaseLogEntryManager, LogEntryQuerySet

from audit_logging.utils import BulkActionModelList

if TYPE_CHECKING:
    from kausal_common.models.types import FK

    from actions.models import Plan


class PlanScopedModelLogEntryManager(BaseLogEntryManager):
    def log_bulk_action(self, instances: BulkActionModelList, action: str, **kwargs):
        if len(instances) == 0:
            return
        data = kwargs.pop('data', None) or {}
        label = kwargs.pop('title', None)
        timestamp = kwargs.pop('timestamp', timezone.now())
        plan = instances.plan
        content_type = ContentType.objects.get_for_model(
            instances[0],
            for_concrete_model=False
        )
        log_entries = [
            PlanScopedModelLogEntry(
                content_type=content_type,
                label=label if label else str(instance),
                action=action,
                timestamp=timestamp,
                data=data,
                plan_id=plan.pk,
                object_id=str(instance.pk),
                **kwargs
            )
            for instance in instances
        ]
        PlanScopedModelLogEntry.objects.bulk_create(log_entries)

    def log_action(self, instance, action, **kwargs):
        if isinstance(instance, BulkActionModelList):
            self.log_bulk_action(instance, action, **kwargs)
            return None

        if instance.pk is None:
            raise ValueError(
                'Attempted to log an action for object %r with empty primary key'
                % (instance,)
            )

        data = kwargs.pop('data', None) or {}
        title = kwargs.pop('title', None)
        if not title:
            title = self.get_instance_title(instance)

        timestamp = kwargs.pop('timestamp', timezone.now())
        kwargs.update(object_id=str(instance.pk))

        plans = instance.get_plans()
        retval = None
        if not plans and 'user' in kwargs:
            plans = [kwargs['user'].get_active_admin_plan()]
        for plan in set(plans):
            kwargs.update(plan=plan)
            retval = PlanScopedModelLogEntry.objects.create(
                content_type=ContentType.objects.get_for_model(
                    instance, for_concrete_model=False
                ),
                label=title,
                action=action,
                timestamp=timestamp,
                data=data,
                **kwargs,
            )
        return retval

    def viewable_by_user(self, user):
        return super().viewable_by_user(user).filter(
            plan__isnull=False,
            plan__in=user.get_adminable_plans()
        )

    def for_instance(self, instance):
        return self.filter(
            content_type=ContentType.objects.get_for_model(
                instance, for_concrete_model=False
            ),
            object_id=str(instance.pk),
        )


class PlanScopedModelLogEntry(BaseLogEntry):
    # The type error below stems from the Wagtail code
    object_id = models.CharField(max_length=255, blank=False, db_index=True)  # type: ignore[assignment]
    plan: FK[Plan] = models.ForeignKey('actions.Plan', null=False, blank=False, on_delete=models.PROTECT)

    objects: ClassVar[PlanScopedModelLogEntryManager] = PlanScopedModelLogEntryManager()  # type: ignore[misc]

    class Meta:
        ordering = ['-timestamp', '-id']
        verbose_name = _('plan scoped model log entry')
        verbose_name_plural = _('plan scoped model log entries')

    def __str__(self):
        return 'PlanScopedModelLogEntry %d: \'%s\' on \'%s\' with id %s' % (
            self.pk,
            self.action,
            self.object_verbose_name(),
            self.object_id,
        )


class PlanScopedPageLogEntryQuerySet(LogEntryQuerySet):
    def get_content_type_ids(self):
        if self.exists():
            return {ContentType.objects.get_for_model(Page).pk}
        return set()

    def filter_on_content_type(self, content_type):
        if content_type == ContentType.objects.get_for_model(Page):
            return self
        return self.none()


class PlanScopedPageLogEntryManager(BaseLogEntryManager):
    def get_queryset(self):
        return PlanScopedPageLogEntryQuerySet(self.model, using=self._db)

    def get_instance_title(self, instance):
        return instance.specific_deferred.get_admin_display_title()

    def log_action(self, instance, action, **kwargs):
        plan = instance.plan
        if plan is None:
            return None

        if instance.pk is None:
            raise ValueError(
                'Attempted to log an action for object %r with empty primary key'
                % (instance,)
            )

        data = kwargs.pop('data', None) or {}
        title = kwargs.pop('title', None)
        if not title:
            title = self.get_instance_title(instance)

        timestamp = kwargs.pop('timestamp', timezone.now())
        kwargs.update(plan=plan, page=instance)

        return PlanScopedPageLogEntry.objects.create(
            content_type=ContentType.objects.get_for_model(
                instance, for_concrete_model=False
            ),
            label=title,
            action=action,
            timestamp=timestamp,
            data=data,
            **kwargs,
        )

    def viewable_by_user(self, user):
        from django.db.models import Q, Subquery
        from wagtail.permissions import page_permission_policy

        explorable_instances = page_permission_policy.explorable_instances(user)
        q = Q(page__in=explorable_instances.values_list('pk', flat=True))

        root_page = Page.get_first_root_node()
        if root_page is None:
            raise ValueError('No root page found')
        root_page_permissions = root_page.permissions_for_user(user)
        if (
            user.is_superuser
            or root_page_permissions.can_add_subpage()
            or root_page_permissions.can_edit()
        ):
            q = q | Q(
                page_id__in=Subquery(
                    PlanScopedPageLogEntry.objects.filter(deleted=True).values('page_id')
                )
            )

        return PlanScopedPageLogEntry.objects.filter(q).filter(
            plan__isnull=False,
            plan__in=user.get_adminable_plans()
        )

    def for_instance(self, instance):
        return self.filter(page=instance)


class PlanScopedPageLogEntry(BaseLogEntry):
    page: FK[Page] = models.ForeignKey(
        'wagtailcore.Page',
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name='+',
    )
    plan: FK[Plan] = models.ForeignKey('actions.Plan', null=False, blank=False, on_delete=models.PROTECT)

    objects = PlanScopedPageLogEntryManager()

    class Meta:
        ordering = ['-timestamp', '-id']
        verbose_name = _('plan scoped page log entry')
        verbose_name_plural = _('plan scoped page log entries')

    def __str__(self):
        return 'PlanScopedPageLogEntry %d: \'%s\' on \'%s\' with id %s' % (
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
