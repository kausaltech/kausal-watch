from __future__ import annotations

from typing import TYPE_CHECKING

from django.utils.translation import gettext_lazy as _
from wagtail import hooks

from . import wagtail_admin  # noqa

if TYPE_CHECKING:
    from wagtail.log_actions import LogActionRegistry


@hooks.register('register_log_actions')
def register_indicator_log_actions(actions: LogActionRegistry):
    actions.register_action('feedback.received', _("Receive feedback"), _("Feedback received"))
    actions.register_action('feedback.processed', _("Mark feedback as processed"), _("Feedback marked as processed"))
    actions.register_action('feedback.unprocessed', _("Unmark feedback as processed"), _("Feedback unmarked as processed"))
