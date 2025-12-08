from __future__ import annotations

from django.db import models
from wagtail import hooks

from pages.models import AplansPage

from .models import PlanScopedModelLogEntry, PlanScopedPageLogEntry


@hooks.register("register_log_actions")
def register_core_log_actions(actions):
    actions.register_model(models.Model, PlanScopedModelLogEntry)
    actions.register_model(AplansPage, PlanScopedPageLogEntry)
