from __future__ import annotations

from celery import shared_task

from actions.models.plan import Plan

from .main import copy_plan as copy_plan_implementation


@shared_task
def copy_plan(
    plan_id: int,
    new_plan_identifier: str,
    new_plan_name: str,
    version_name: str,
    supersede_original_plan: bool,
    supersede_original_actions: bool,
    copy_indicators: bool,
):
    plan = Plan.objects.get(id=plan_id)
    copy_plan_implementation(
        plan=plan,
        new_plan_identifier=new_plan_identifier,
        new_plan_name=new_plan_name,
        version_name=version_name,
        supersede_original_plan=supersede_original_plan,
        supersede_original_actions=supersede_original_actions,
        copy_indicators=copy_indicators,
    )
