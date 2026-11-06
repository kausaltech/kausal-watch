"""
Validation rules for action and task dates, shared by the admin forms and the REST serializers.

Neither rule lives in the models' `clean()`, because both must only apply when a save changes one of
the dates involved: existing rows break them, and a user who edits an unrelated field of such a row
(or who may not even see the date, due to field customization) must not get stuck on an error about
it. Only the form or serializer knows what the save changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from datetime import date

    from django_stubs_ext import StrPromise

    from actions.models import Plan


ACTION_END_BEFORE_START_MESSAGE = _("The end date can't be before the start date")
TASK_COMPLETED_IN_FUTURE_MESSAGE = _("The completion date can't be in the future")


def get_action_dates_error(start_date: date | None, end_date: date | None) -> StrPromise | None:
    """Return the error for an action's start and end date, or None if they are consistent."""
    if start_date is None or end_date is None:
        return None
    if start_date <= end_date:
        return None
    return ACTION_END_BEFORE_START_MESSAGE


def get_task_completion_date_error(completed_at: date | None, plan: Plan) -> StrPromise | None:
    """Return the error for a task's completion date, or None if it is not later than today in the plan's time zone."""
    if completed_at is None:
        return None
    if completed_at <= plan.now_in_local_timezone().date():
        return None
    return TASK_COMPLETED_IN_FUTURE_MESSAGE
