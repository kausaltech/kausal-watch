from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils import timezone
from wagtail.models import ModelLogEntry, PageLogEntry, PageLogEntryManager
from wagtail.models.audit_log import ModelLogEntryManager

from audit_logging.utils import BulkActionModelList


class PlanScopedModelLogEntryManager(ModelLogEntryManager):
    def log_bulk_action(self, instance: BulkActionModelList, action: str, **kwargs):
        if len(instance) == 0:
            return
        data = kwargs.pop("data", None) or {}
        title = kwargs.pop("title", None)
        timestamp = kwargs.pop("timestamp", timezone.now())
        content_type=ContentType.objects.get_for_model(
            instance[0],
            for_concrete_model=False
        )
        log_entries = [
            PlanScopedModelLogEntry(
                content_type=content_type,
                label=title,
                action=action,
                timestamp=timestamp,
                data=data,
                **kwargs
            )
        ]
        self.model.objects.bulk_create(
            log_entries
        )

    def log_action(self, instance, action, **kwargs):
        if isinstance(instance, BulkActionModelList):
            self.log_bulk_action(instance, action, **kwargs)
        plans=instance.get_plans()
        retval = None
        if not plans and 'user' in kwargs:
            # We end up here in cases like newly created root organizations where
            # the plan.related_organizations is not set yet when logging
            plans = [kwargs['user'].get_active_admin_plan()]
        for plan in set(plans):
            kwargs.update(plan=plan)
            retval = super().log_action(instance, action, **kwargs)
        # Notice that even though wagtail returns the created
        # log entry, no caller seems to be doing anything with
        # it currently. Hence, it might be good enought to return
        # one of the several created log entries.
        return retval

    def viewable_by_user(self, user):
        return super().viewable_by_user(user).filter(
            plan__isnull=False,
            plan__in=user.get_adminable_plans()
        )


class PlanScopedModelLogEntry(ModelLogEntry):
    objects = PlanScopedModelLogEntryManager()
    plan = models.ForeignKey('actions.Plan', null=False, blank=False, on_delete=models.PROTECT)
    modellogentry_migration_instance = models.OneToOneField(
        'wagtailcore.ModelLogEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )


class PlanScopedPageLogEntryManager(PageLogEntryManager):
    def log_action(self, instance, action, **kwargs):
        plan = instance.plan
        if plan is None:
            # Plan can be none if it's a root page and the site has not
            # been created yet
            return None
        kwargs.update(plan=plan)
        return super().log_action(instance, action, **kwargs)

    def viewable_by_user(self, user):
        qs = super().viewable_by_user(user)
        return qs.filter(
            planscopedpagelogentry__isnull=False,
            planscopedpagelogentry__plan__in=user.get_adminable_plans()
        )


class PlanScopedPageLogEntry(PageLogEntry):
    objects = PlanScopedPageLogEntryManager()
    plan = models.ForeignKey('actions.Plan', null=False, blank=False, on_delete=models.PROTECT)
    pagelogentry_migration_instance = models.OneToOneField(
        'wagtailcore.PageLogEntry',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )
