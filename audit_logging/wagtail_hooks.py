from __future__ import annotations

from django.db import models
from wagtail import hooks

from pages.models import AplansPage

from actions.models.plan import Plan
from aplans.utils import PlanRelatedModel
from .models import PlanScopedModelLogEntry, PlanScopedPageLogEntry


@hooks.register("register_log_actions")
def register_core_log_actions(actions):
    actions.register_model(Plan, PlanScopedModelLogEntry)
    actions.register_model(PlanRelatedModel, PlanScopedModelLogEntry)
    actions.register_model(AplansPage, PlanScopedPageLogEntry)
