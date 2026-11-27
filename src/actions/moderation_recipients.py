"""Who reviews an action at its current moderation step; both the emails and the inbox notify them."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.db.models import Q
from wagtail.models import AbstractGroupApprovalTask

from users.models import User

from .models import Action, ActionContactPerson
from .models.action import ActionModeratorApprovalTask

if TYPE_CHECKING:
    from collections.abc import Sequence

    from wagtail.models import TaskState

    from .permission_policy import ActionPermissionPolicy


def _moderators(action: Action) -> Sequence[User]:
    moderator_ids = action.contact_persons.filter(ActionContactPerson.moderators_q()).values_list('person__user')
    return list(User.objects.filter(id__in=moderator_ids))


def _group_members_who_can_edit(task: AbstractGroupApprovalTask, action: Action) -> Sequence[User]:
    # Global groups span all plans, so keep the members who have a role in the action's plan
    has_role = (
        Q(person__general_admin_plans=action.plan)
        | Q(person__contact_for_actions=action)
        | Q(person__organization_plan_admins__plan=action.plan)
    )
    candidates = User.objects.filter(groups__in=task.groups.all(), is_active=True).filter(has_role).distinct()
    policy = cast('ActionPermissionPolicy', Action.permission_policy())
    return [user for user in candidates if policy.user_has_permission_in_own_plan(user, 'change', action)]


def get_step_reviewers(task_state: TaskState, exclude: User | None = None) -> Sequence[User]:
    action = task_state.workflow_state.content_object
    if not isinstance(action, Action):
        return []
    task = task_state.task.specific
    if isinstance(task, ActionModeratorApprovalTask):
        reviewers = _moderators(action)
    elif isinstance(task, AbstractGroupApprovalTask):
        reviewers = _group_members_who_can_edit(task, action)
    else:
        return []
    return [user for user in reviewers if exclude is None or user.pk != exclude.pk]
