from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from actions.models import Action, ActionTask
    from actions.models.public_user import PublicUser
    from feedback.models import UserFeedback
    from indicators.models import Indicator
    from notifications.models import ManuallyScheduledNotificationTemplate

    type NotificationObject = Action | ActionTask | Indicator | UserFeedback | PublicUser | ManuallyScheduledNotificationTemplate
