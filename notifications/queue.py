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
    # Group first by recipient, then by type.
    # In the future, we might want to abstract this from the user and provide a nice interface for getting the data in
    # various ways.
    items_for_recipient: Dict[NotificationRecipient, Dict[NotificationType, List[NotificationQueueItem]]]

    def __init__(self):
        self.items_for_recipient = {}

    def push(self, item: NotificationQueueItem):
        items_for_type = self.items_for_recipient.setdefault(item.recipient, {})
        items_for_type.setdefault(item.notification.type, []).append(item)
