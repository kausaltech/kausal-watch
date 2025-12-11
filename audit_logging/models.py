from __future__ import annotations

from django.db import models
from wagtail.models import ModelLogEntry, PageLogEntry
from wagtail.models import PageLogEntryManager
from wagtail.models.audit_log import ModelLogEntryManager



class PlanScopedModelLogEntryManager(ModelLogEntryManager):
    def log_action(self, instance, action, **kwargs):
        plans=instance.get_plans()
        retval = None
        for plan in plans:
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


class PlanScopedPageLogEntryManager(PageLogEntryManager):
    def log_action(self, instance, action, **kwargs):
        plan = instance.plan
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
