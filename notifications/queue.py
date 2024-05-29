from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Dict, List

from .models import NotificationType
from .notifications import Notification

if typing.TYPE_CHECKING:
    from .recipients import NotificationRecipient


@dataclass
class NotificationQueueItem:
    notification: Notification
    recipient: NotificationRecipient


class NotificationQueue:
    # Group first by recipient, then by type, then by identifier.
    # The identifier is needed for manually scheduled notifications to distinguish
    # between the differing templates for each instance of them.
    # In the future, we might want to abstract this from the user and provide a nice interface for getting the data in
    # various ways.
    items_for_recipient: Dict[NotificationRecipient, Dict[NotificationType, Dict[str | None, List[NotificationQueueItem]]]]

    def __init__(self):
        self.items_for_recipient = {}

    def push(self, item: NotificationQueueItem):
        items_for_type = self.items_for_recipient.setdefault(item.recipient, {})
        _type = item.notification.type
        items_for_identifier = items_for_type.setdefault(_type, {})
        identifier = item.notification.get_identifier()
        items_for_identifier.setdefault(identifier, []).append(item)
