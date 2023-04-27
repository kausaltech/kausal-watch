from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from actions.models import Action, ActionTask
    from feedback.models import UserFeedback
    from indicators.models import Indicator

    NotificationObject: typing.TypeAlias = typing.Union[Action, ActionTask, Indicator, UserFeedback]
