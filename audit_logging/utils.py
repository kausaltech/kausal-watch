from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Model

if TYPE_CHECKING:
    from actions.models import Plan


class BulkActionModelList(list[Model]):
    """
    Provide a type-safe way to pass lists of model instances to audit logging.

    We are registering this model (instead of list) in Wagtail's log actions registry
    so that we can handle the case of bulk creating model log entry instances
    within our application when bulk operations are executed in the REST API.
    """
    plan: Plan

    def __init__(self, *args, plan: Plan, **kwargs):
        super().__init__(*args, **kwargs)
        self.plan = plan

    def get_plans(self):
        return [self.plan]
