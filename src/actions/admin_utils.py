import typing

from django.urls import reverse

if typing.TYPE_CHECKING:
    from actions.models import Action


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
