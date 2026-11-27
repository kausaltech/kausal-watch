import typing

from django.urls import reverse

if typing.TYPE_CHECKING:
    from collections.abc import Callable

    from actions.models import Action
    from users.models import User


def change_log_message_url_or_none(action: Action, moderation_enabled: bool = False) -> str | None:
    plan = action.plan
    if not plan.features.enable_change_log:
        return None
    change_log_create_url = reverse('wagtailsnippets_actions_actionchangelogmessage:add')
    if moderation_enabled:
        # Get the revision that was just created for this submission
        revision = action.latest_revision
    else:
        # Get the live revision
        revision = action.live_revision or action.latest_revision
    revision_param = f'&revision={revision.pk}' if revision else ''
    return f'{change_log_create_url}?action={action.pk}{revision_param}'


def get_change_log_message_revision_check(user: User, action: Action) -> Callable[[int | None], bool]:
    """
    Return a check whether the user may write, change or delete a change history message of the action tied to a revision.

    With moderation, text shown on the public site must have been approved. Users who can't publish the action may
    therefore only write messages for changes that are waiting for moderation. The check takes the revision's ID.
    """
    if not action.plan.features.enable_moderation_workflow or user.can_publish_action(action):
        return lambda _revision_id: True
    pending_revision_id = action.latest_revision_id if action.workflow_in_progress else None
    return lambda revision_id: revision_id is not None and revision_id == pending_revision_id


def may_write_change_log_message(user: User, action: Action, revision_id: int | None) -> bool:
    return get_change_log_message_revision_check(user, action)(revision_id)


def is_locked_for_user(action: Action, user: User) -> bool:
    """Return whether the action is locked for the user, e.g. while it awaits moderation by others."""
    lock = action.get_lock()
    return lock is not None and lock.for_user(user)


def get_change_log_message_change_check(user: User, action: Action) -> Callable[[int | None], bool]:
    """
    Return a check whether the user may edit or delete a change history message of the action tied to a revision.

    On top of the rule for writing messages, this respects the action's lock: while the action awaits moderation, only
    its reviewers may change what they review. Adding a message stays possible, since submitting changes for moderation
    leads to adding one. The check takes the revision's ID.
    """
    if is_locked_for_user(action, user):
        return lambda _revision_id: False
    return get_change_log_message_revision_check(user, action)


def may_change_change_log_message(user: User, action: Action, revision_id: int | None) -> bool:
    return get_change_log_message_change_check(user, action)(revision_id)
